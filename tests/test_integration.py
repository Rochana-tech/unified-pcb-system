import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi.testclient import TestClient
from integration.api import create_app
from integration.runtime import Runtime
from integration.config import Settings, line_config
from integration.flow import Flow
from integration.contracts import Telemetry
from integration.explanations import explain_incident
from layers.layer3.models import MachineState, MachineStatus, FaultEvent, FaultStatus
from layers.layer3.interfaces import ProductionLineService
from layers.layer3.simulation import WhatIfSimulator, ScenarioSpec, ScenarioKind

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        self.runtimes=[]

    def tearDown(self):
        for r in self.runtimes:
            r.close()

    def runtime(self,mode='demo',backup=True,db=':memory:'):
        r=Runtime(Settings(mode,db,2,backup),clock=lambda:self.now)
        self.runtimes.append(r)
        return r

    def advance(self,r,seconds):
        for _ in range(seconds):
            self.now+=timedelta(seconds=1)
            r.tick()

    def telemetry(self,mid='M4',**changes):
        data=dict(machine_id=mid,timestamp=self.now,status='RUNNING',units_processed_total=10,
            queue_length=2,cycle_time_sec=8,capacity_units_per_hour=450)
        data.update(changes)
        return Telemetry(**data)

    def test_sensor_readings_reach_real_ann(self):
        r=self.runtime()
        self.assertTrue(all(v['fault_type']=='NORMAL' for v in r.predictions.values()))
        r.inject('M4','BEARING_FAULT')
        self.assertEqual(r.predictions['M4']['fault_type'],'BEARING_FAULT')
        self.assertEqual(r.twin.get_machine_snapshot('M4')['effective_capacity_units_per_hour'],0)
        self.assertEqual(len(r.incidents),1)

    def test_repeated_fault_does_not_restart_deadline(self):
        r=self.runtime();r.inject('M4','BEARING_FAULT')
        d=next(iter(r.incidents.values()))['decision'];deadline=d.correction_deadline
        self.advance(r,1)
        self.assertEqual(len(r.incidents),1)
        self.assertEqual(d.correction_deadline,deadline)

    def test_timeout_simulates_and_applies_route(self):
        r=self.runtime();r.inject('M4','BEARING_FAULT')
        self.advance(r,3)
        d=next(iter(r.incidents.values()))['decision']
        self.assertEqual(d.status.value,'reallocated')
        self.assertEqual(r.flow.routes['M4'],'M4-BACKUP')
        self.advance(r,30)
        self.assertGreater(r.flow.stations['M4-BACKUP'].completed,0)
        self.assertEqual(r.flow.admitted,r.flow.finished+r.flow.wip())
        self.assertEqual(r.flow.routes['M5'],'M5') # Packaging was not skipped.

    def test_human_correction_before_timeout(self):
        r=self.runtime();r.inject('M4','BEARING_FAULT')
        result=r.correct('M4');self.assertTrue(result['in_time'])
        self.advance(r,5)
        self.assertEqual(r.flow.routes['M4'],'M4')
        self.assertEqual(next(iter(r.incidents.values()))['decision'].status.value,'resumed_by_human')

    def test_late_correction_not_counted_in_time(self):
        r=self.runtime();r.inject('M4','BEARING_FAULT')
        self.now+=timedelta(seconds=3)
        result=r.correct('M4')
        self.assertFalse(result['in_time'])
        self.assertEqual(r.flow.routes['M4'],'M4-BACKUP')
        self.assertFalse(r.flow.stations['M4'].down)

    def test_no_standby_fails_without_inventing_machine(self):
        r=self.runtime(backup=False);r.inject('M4','BEARING_FAULT');self.advance(r,3)
        d=next(iter(r.incidents.values()))['decision']
        self.assertEqual(d.status.value,'no_alternative_flagged')
        self.assertIsNone(d.alternative_machine_id)
        self.assertEqual(r.flow.routes['M4'],'M4')

    def test_packaging_cannot_replace_soldering(self):
        r=self.runtime();r.inject('M2','MOTOR_OVERHEAT');self.advance(r,3)
        self.assertEqual(next(iter(r.incidents.values()))['decision'].status.value,'no_alternative_flagged')
        self.assertEqual(r.flow.routes['M2'],'M2')

    def test_simulation_isolation_and_reproducibility(self):
        r=self.runtime()
        before=copy.deepcopy(r.flow.__dict__)
        a=r.compare('M4',900,15,True);b=r.compare('M4',900,15,True)
        self.assertEqual(r.flow.__dict__,before)
        self.assertEqual(a['baseline'],b['baseline'])
        self.assertEqual(a['recovery'],b['recovery'])
        self.assertGreater(a['recovery']['throughput_units_per_hour'],a['baseline']['throughput_units_per_hour'])

    def test_transfer_keeps_full_queue_within_buffer(self):
        flow=Flow(line_config(True),seed_wip=False)
        s=flow.stations['M4']
        s.queue=12
        s.active=True
        s.remaining=4
        flow.admitted=13
        flow.reallocate('M4','M4-BACKUP')
        self.assertEqual(flow.stations['M4-BACKUP'].queue,12)
        self.assertTrue(flow.stations['M4-BACKUP'].active)
        self.assertEqual(flow.admitted,flow.wip())

    def test_flow_conservation_blocking_and_starvation(self):
        flow=Flow(line_config(True))
        flow.stations['M4'].down=True
        flow.step(240)
        self.assertLessEqual(max(s.queue for s in flow.stations.values()),flow.buffer_limit)
        self.assertEqual(flow.stations['M3'].status,'BLOCKED')
        self.assertEqual(flow.stations['M5'].status,'IDLE')
        self.assertEqual(flow.admitted,flow.finished+flow.wip())
        flow.reallocate('M4','M4-BACKUP');flow.step(120)
        self.assertEqual(flow.admitted,flow.finished+flow.wip())
        self.assertGreater(flow.finished,10)

    def test_controller_only_data_remains_usable(self):
        r=self.runtime('external');r.ingest(self.telemetry())
        row=r.snapshot()['machines'][3]
        self.assertFalse(row['stale'])
        self.assertEqual(row['fault_status'],'UNKNOWN')
        self.assertIsNone(row['prediction'])
        self.assertIsNone(row['risk_prediction'])

    def test_controller_fault_is_not_invented_ann_result(self):
        r=self.runtime('external');r.ingest(self.telemetry(status='DOWN'))
        d=next(iter(r.incidents))
        result=explain_incident(r,d)
        self.assertEqual(len(result['answers']),8)
        self.assertFalse(any(e['source']=='ann_fault_detection' for e in result['evidence']))
        self.assertFalse(result['control_actions_executed'])

    def test_duplicate_old_and_future_telemetry_rejected(self):
        r=self.runtime('external');r.ingest(self.telemetry())
        for timestamp in [self.now,self.now-timedelta(seconds=31),self.now+timedelta(seconds=10)]:
            with self.assertRaises(ValueError):
                r.ingest(self.telemetry(timestamp=timestamp))

    def test_counter_reset_does_not_produce_false_throughput(self):
        r=self.runtime('external');r.ingest(self.telemetry(units_processed_total=100))
        self.now+=timedelta(seconds=2);r.ingest(self.telemetry(units_processed_total=2))
        self.assertEqual(r.twin.get_machine_snapshot('M4')['throughput_units_per_hour'],0)

    def test_fresh_fault_does_not_mask_stale_production(self):
        twin=ProductionLineService(line_config(False))
        old=datetime.now(timezone.utc)-timedelta(seconds=120)
        twin.ingest_machine_state(MachineState('M4',MachineStatus.RUNNING,timestamp=old))
        twin.ingest_fault_event(FaultEvent('M4',FaultStatus.OK))
        twin.refresh()
        self.assertTrue(twin.get_machine_snapshot('M4')['stale'])
        self.assertEqual(twin.get_machine_snapshot('M4')['effective_capacity_units_per_hour'],0)

    def test_legacy_whatif_preserves_zero_capacity(self):
        r=self.runtime()
        metrics=r.twin.twin.clone_metrics_for_simulation()
        metrics['M4'].effective_capacity_units_per_hour=0
        sim=WhatIfSimulator(metrics,['M1','M2','M3','M4','M5'])
        result=sim.run(ScenarioSpec('No capacity',ScenarioKind.REDUCED_CAPACITY,'M4',factor=1),duration_hr=1)
        self.assertEqual(result.line_throughput_units_per_hour,0)

    def test_explanation_compares_actual_backend_results(self):
        r=self.runtime();r.inject('M4','BEARING_FAULT');self.advance(r,3)
        result=explain_incident(r,next(iter(r.incidents)))
        self.assertEqual(len(result['answers']),8)
        self.assertEqual(result['comparison']['status'],'comparable')
        self.assertGreater(result['comparison']['throughput_difference'],0)
        self.assertFalse(result['control_actions_executed'])
        self.assertTrue(any('repair duration' in w for w in result['warnings']))

    def test_api_contract_validation_and_websocket(self):
        r=self.runtime()
        with TestClient(create_app(runtime=r,start_background=False)) as client:
            self.assertEqual(client.get('/').status_code,200)
            self.assertEqual(client.get('/api/machines/unknown').status_code,404)
            self.assertEqual(client.post('/api/scenarios/compare',json={'downtime_seconds':-1}).status_code,422)
            self.assertEqual(client.post('/api/demo/fault/M4',json={'fault_type':'invented'}).status_code,422)
            self.assertEqual(client.post('/api/demo/fault/M4',json={'fault_type':'BEARING_FAULT'}).status_code,200)
            with client.websocket_connect('/ws/dashboard') as ws:
                snapshot=ws.receive_json()
                self.assertEqual(snapshot['decisions'][0]['machine_id'],'M4')
            did=next(iter(r.incidents))
            self.assertEqual(client.get('/api/alerts/'+did+'/explanation').status_code,200)
            self.assertEqual(client.post('/api/scenarios/compare',json={}).status_code,200)

    def test_api_external_sensor_validation(self):
        r=self.runtime('external')
        with TestClient(create_app(runtime=r,start_background=False)) as client:
            data=self.telemetry().model_dump(mode='json')
            data['sensors']={'current':5}
            self.assertEqual(client.post('/api/telemetry',json=data).status_code,422)
            data.pop('sensors')
            self.assertEqual(client.post('/api/telemetry',json=data).status_code,202)
            self.assertEqual(client.post('/api/demo/reset').status_code,409)

    def test_sqlite_history_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/'events.db')
            r=Runtime(Settings(database=path));r.inject('M4','STOPPED');r.close()
            r=Runtime(Settings(database=path))
            try:
                self.assertTrue(any(e['kind']=='demo_fault_injected' for e in r.store.recent(100)))
                self.assertEqual(len(r.incidents),0) # New session; never silently restore old timers.
            finally:r.close()

if __name__=='__main__':
    unittest.main()

