from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import random
import threading
import uuid

from layers.layer1.machine_stream.state_manager import StateManager
from layers.layer2a.inference.predictor import FaultPredictor
from layers.layer2a.data.generate_synthetic import CLASS_PROFILES
from layers.layer3.interfaces import ProductionLineService
from layers.layer3.models import MachineState, MachineStatus, FaultEvent, FaultStatus
from layers.layer4.recovery_engine import RecoveryEngine
from layers.layer4.models import FaultEvent as RecoveryFault
from layers.layer4.config import IndustryConfig
from layers.layer4.timer_manager import CorrectionTimerManager
from .config import Settings, TOPOLOGY, line_config
from .contracts import Telemetry
from .flow import Flow
from .storage import Store, AuditLogger
from .bridge import Bridge

class Runtime:
    def __init__(self, settings=Settings(), clock=None):
        if settings.mode not in ('demo', 'external'):
            raise ValueError('Mode must be demo or external')
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.lock = threading.RLock()
        self.config = line_config(settings.demo_backup and settings.mode == 'demo')
        self.flow = Flow(self.config, seed_wip=settings.mode == 'demo')
        self.acquisition = StateManager([m.machine_id for m in self.config.machines])
        self.twin = ProductionLineService(self.config)
        self.twin.integration._stale_after = timedelta(seconds=settings.stale_seconds)
        self.predictor = FaultPredictor('electronics_pcb')
        self.store = Store(settings.database)
        self.latest = {}
        self.predictions = {}
        self.incidents = {}
        self.latched = set()
        self.comparisons = {}
        self.histories = {m.machine_id:deque(maxlen=60) for m in self.config.machines}
        self.rng = random.Random(42)
        self.tick_count = 0
        self.last_tick_at = None
        self.error = None
        self.mqtt_status = 'disabled'
        bridge = Bridge(self)
        recovery_config = IndustryConfig('PCB assembly', {'testing':['testing']},
            {s.machine_id:s.default_capacity_uph for s in self.config.machines},
            ['placement','soldering','inspection','testing','packaging'],
            settings.correction_seconds, 4, .85)
        self.recovery = RecoveryEngine(recovery_config,bridge,bridge,bridge,bridge,bridge,
            AuditLogger(self.store), CorrectionTimerManager(lambda:self.clock().replace(tzinfo=None)))
        self.store.add('session_started', {'mode':settings.mode,'backup_simulated':len(self.config.machines)>5})
        if settings.mode == 'demo':
            self.publish_demo()

    def publish_demo(self):
        timestamp = self.clock()
        for mid, station in self.flow.stations.items():
            profile = CLASS_PROFILES.get(station.fault, CLASS_PROFILES['NORMAL'])
            sensors = {key:round(max(0,mean+self.rng.gauss(0,std*.03)),4)
                       for key,(mean,std) in profile.items()} if station.fault != 'STOPPED' else None
            record = dict(machine_id=mid,timestamp=timestamp.isoformat(),status=station.status,
                units_processed_total=station.completed,queue_length=station.queue,
                cycle_time_sec=station.processing_time if station.capacity else station.cycle,
                capacity_units_per_hour=station.capacity,downtime_seconds=station.downtime,sensors=sensors)
            self._ingest(record, demo=True)
        self.twin.refresh()
        self._detect_incidents()
        self._history()

    def _ingest(self, record, demo=False):
        mid = record['machine_id']
        timestamp = datetime.fromisoformat(record['timestamp'].replace('Z','+00:00'))
        self.latest[mid] = record
        self.acquisition.update_production(record)
        self.twin.ingest_machine_state(MachineState(mid,MachineStatus(record['status']),
            cycle_time_sec=record['cycle_time_sec'],units_processed_total=record['units_processed_total'],
            queue_length=record['queue_length'],capacity_units_per_hour=record['capacity_units_per_hour'],
            timestamp=timestamp))
        sensors = record.get('sensors')
        if sensors:
            reading = dict(machine_id=mid,timestamp=record['timestamp'],**sensors)
            self.acquisition.update_sensor(reading)
            prediction = self.predictor.predict(reading).as_dict()
            self.predictions[mid] = prediction
            status = FaultStatus.FAULT if prediction['fault_status'] == 'FAULT' else FaultStatus.OK
            self.twin.ingest_fault_event(FaultEvent(mid,status,prediction['fault_type'],prediction['confidence'],timestamp))
        else:
            self.predictions.pop(mid, None)
            # Missing sensors are UNKNOWN, never a fabricated NORMAL ANN result.
            self.twin.ingest_fault_event(FaultEvent(mid,FaultStatus.UNKNOWN,timestamp=timestamp))

    def ingest(self, telemetry: Telemetry):
        with self.lock:
            if self.settings.mode != 'external':
                raise ValueError('External telemetry requires --mode external; demo data is kept separate')
            mid = telemetry.machine_id
            now = self.clock()
            age = (now-telemetry.timestamp).total_seconds()
            if age > self.settings.stale_seconds or age < -5:
                raise ValueError('Telemetry is stale or more than 5 seconds in the future')
            old = self.latest.get(mid)
            if old and telemetry.timestamp <= datetime.fromisoformat(old['timestamp']):
                raise ValueError('Duplicate or out-of-order timestamp')
            if old and telemetry.units_processed_total < old['units_processed_total']:
                self.store.add('counter_reset', {'machine_id':mid,'previous':old['units_processed_total'],
                    'current':telemetry.units_processed_total})
            self._ingest(telemetry.model_dump(mode='json'))
            self.twin.refresh()
            self._detect_incidents()
            self._history()
            self.store.add('telemetry', telemetry.model_dump(mode='json'))
            return {'accepted':True,'machine_id':mid,'timestamp':telemetry.timestamp.isoformat()}

    def _detect_incidents(self):
        for mid, record in self.latest.items():
            prediction = self.predictions.get(mid)
            down = record['status'] in ('DOWN','MAINTENANCE')
            fault = bool(prediction and prediction['fault_status'] == 'FAULT' and prediction['confidence'] >= .6)
            if not down and not fault:
                # Once an incident is resolved, a later new fault may start a new timer.
                if not self.recovery.get_pending_fault(mid):
                    self.latched.discard(mid)
                continue
            if mid in self.latched:
                continue
            kind = prediction['fault_type'] if fault else 'CONTROLLER_UNAVAILABLE'
            source = 'ANN' if fault else 'controller'
            event = RecoveryFault('FAULT-'+uuid.uuid4().hex[:10],mid,kind,
                prediction['confidence'] if fault else 1.0,record.get('sensors') or {},record['timestamp'])
            decision = self.recovery.on_fault_detected(event)
            self.incidents[decision.decision_id] = {'decision':decision,'record':dict(record),
                'prediction':prediction if fault else None,'source':source}
            self.latched.add(mid)

    def _history(self):
        for mid, record in self.latest.items():
            history = self.histories[mid]
            if not history or history[-1]['timestamp'] != record['timestamp']:
                history.append(dict(timestamp=record['timestamp'],queue=record['queue_length'],
                    units=record['units_processed_total'],sensors=record.get('sensors')))

    def tick(self, seconds=1.0):
        with self.lock:
            if self.settings.mode == 'demo':
                self.flow.step(seconds)
                self.publish_demo()
            else:
                self.twin.refresh()
            # External observations never trigger actual hardware actuation.
            self.recovery.check_expirations()
            self.tick_count += 1
            self.last_tick_at = self.clock().isoformat()
            if self.tick_count % 10 == 0:
                self.store.add('line_snapshot',self.twin.get_line_snapshot())

    def inject(self, mid, fault_type):
        with self.lock:
            if self.settings.mode != 'demo':
                raise ValueError('Fault injection is available only in demo mode')
            if mid not in TOPOLOGY:
                raise ValueError('Unknown production station')
            s = self.flow.stations[mid]
            if mid in self.latched or self.flow.routes[mid] != mid:
                raise ValueError('Resolve or reset the existing demo incident first')
            s.fault = fault_type
            s.down = True
            s.status = 'DOWN'
            self.publish_demo()
            self.store.add('demo_fault_injected',{'machine_id':mid,'fault_type':fault_type})
            return {'injected':True,'machine_id':mid,'simulated':True}

    def correct(self, mid):
        with self.lock:
            if mid not in TOPOLOGY:
                raise ValueError('Unknown production station')
            # Resolve any expired timer before a late repair changes availability.
            self.recovery.check_expirations()
            if self.settings.mode == 'demo':
                s = self.flow.stations[mid]
                s.fault, s.down, s.status = 'NORMAL', False, 'IDLE'
                self.publish_demo()
            else:
                row = self.twin.get_machine_snapshot(mid)
                record = self.latest.get(mid)
                if not row or row['stale'] or not record or record['status'] not in ('RUNNING','IDLE'):
                    raise ValueError('A fresh RUNNING/IDLE controller reading is required to confirm correction')
                if row['fault_status'] == 'FAULT':
                    raise ValueError('ANN still reports a fault')
            decision = self.recovery.on_human_correction(mid)
            self.recovery.check_expirations()
            self.store.add('operator_correction', {'machine_id':mid,'in_time':bool(decision)})
            return {'corrected':True,'in_time':bool(decision),
                'routing':dict(self.flow.routes) if self.settings.mode=='demo' else None,
                'message':'Machine restored; any existing standby route is retained.'}

    def reset_demo(self):
        with self.lock:
            if self.settings.mode != 'demo':
                raise ValueError('Reset is only available in demo mode')
            # Keep audit history; cancel pending incidents with an explicit reset outcome.
            for incident in self.incidents.values():
                d = incident['decision']
                if d.status.value == 'awaiting_correction':
                    self.recovery.timers.cancel(d.machine_id)
                    self.recovery._cleanup(d.machine_id)
                    d.actions_taken.append('demo_reset_cancelled_incident')
                    incident['reset'] = True
            self.incidents.clear()
            self.latched.clear()
            self.comparisons.clear()
            self.flow = Flow(self.config)
            self.twin = ProductionLineService(self.config)
            self.twin.integration._stale_after = timedelta(seconds=self.settings.stale_seconds)
            self.histories = {m.machine_id:deque(maxlen=60) for m in self.config.machines}
            self.store.add('demo_reset',{})
            self.publish_demo()
            return {'reset':True}

    def ranking(self):
        active = set(self.flow.routes.values()) if self.settings.mode == 'demo' else set(TOPOLOGY)
        return [r for r in self.twin.get_bottleneck_ranking() if r['machine_id'] in active]

    def comparison_flow(self):
        if self.settings.mode == 'demo':
            return self.flow.clone()
        result = Flow(self.config,seed_wip=False)
        for mid in TOPOLOGY:
            row = self.twin.get_machine_snapshot(mid)
            if not row or row['stale'] or mid not in self.latest:
                raise ValueError('What-if requires fresh controller data for every station')
            s = result.stations[mid]
            s.queue = row['queue_length']
            s.capacity = row['capacity_units_per_hour']
            s.cycle = row['processing_time_sec']
            s.down = row['machine_status'] in ('DOWN','MAINTENANCE')
            s.active = row['machine_status'] in ('RUNNING','BLOCKED')
            s.remaining = 0 if row['machine_status']=='BLOCKED' else s.processing_time
        result.admitted = result.wip()
        result.buffer_limit = max(12, max(s.queue for s in result.stations.values()))
        return result

    def compare(self, mid, downtime_seconds=120, horizon_minutes=15, use_backup=True):
        with self.lock:
            base = self.comparison_flow()
            if base.routes[mid] != mid:
                raise ValueError('Workload is already on the standby; reset the demo for a new comparison')
            base.stations[mid].down = True
            recovery = base.clone()
            recovery_result = None
            reason = 'No configured compatible standby'
            if use_backup and mid == 'M4' and 'M4-BACKUP' in base.stations:
                try:
                    recovery.reallocate(mid,'M4-BACKUP')
                    recovery_result = recovery.simulate(horizon_minutes*60)
                    reason = 'Compatible simulated testing standby'
                except ValueError as exc:
                    reason = str(exc)
            baseline_result = base.simulate(horizon_minutes*60, downtime_seconds, mid)
            return {'simulation':True,'machine_id':mid,'generated_at':self.clock().isoformat(),
                'starting_state_id':'STATE-'+uuid.uuid4().hex[:10],
                'horizon_minutes':horizon_minutes,'downtime_seconds':downtime_seconds,
                'baseline':baseline_result,'recovery':recovery_result,
                'alternative_machine_id':'M4-BACKUP' if recovery_result else None,
                'alternative_reason':reason,
                'assumptions':['Deterministic single-server stages, 0.25-second steps.',
                    'Finite buffers: '+str(base.buffer_limit)+' waiting boards per station; arrivals 500 boards/hour.',
                    'Existing queued and in-process boards are included; interrupted tests restart on the standby.',
                    'Baseline resumes after the entered downtime; standby scenario assumes immediate transfer and no setup time.',
                    'All boards pass inspection; rework and rejects are not modeled.',
                    'External mode assumes a full remaining cycle for each running station; actual progress is unknown.',
                    'In external mode a board held inside a stopped machine is unknown and excluded; only reported queues and RUNNING/BLOCKED active work are modeled.']}

    def snapshot(self):
        with self.lock:
            self.twin.refresh()
            machines = self.twin.get_line_snapshot()['machines']
            for row in machines:
                mid = row['machine_id']
                row['telemetry'] = self.latest.get(mid)
                row['prediction'] = self.predictions.get(mid)
                row['history'] = list(self.histories[mid])
                row['risk_prediction'] = None
                if self.settings.mode == 'demo':
                    s = self.flow.stations[mid]
                    row['busy_fraction'] = min(1,s.busy_seconds/self.flow.elapsed) if self.flow.elapsed else 0
            decisions = [asdict(v['decision']) for v in self.incidents.values()]
            return {'schema_version':'1.0','mode':self.settings.mode,'generated_at':self.clock().isoformat(),
                'connection':{'last_tick_at':self.last_tick_at,'error':self.error,'mqtt':self.mqtt_status},
                'line_name':'PCB assembly','topology':TOPOLOGY,
                'routes':dict(self.flow.routes) if self.settings.mode=='demo' else {m:m for m in TOPOLOGY},
                'machines':machines,'bottlenecks':self.ranking(),'decisions':decisions,
                'finished_units':self.flow.finished if self.settings.mode=='demo' else
                    self.latest.get('M5',{}).get('units_processed_total'),
                'wip':self.flow.wip() if self.settings.mode=='demo' else None,
                'correction_seconds':self.settings.correction_seconds,
                'model':{'name':'MLPClassifier','training_data':'synthetic electronics_pcb',
                    'purpose':'current fault classification','failure_prediction':'unavailable: trained models not supplied'},
                'recent_events':self.store.recent(30)}

    def close(self):
        self.store.close()

