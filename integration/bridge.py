from layers.layer4.models import MachineState, MachineStatus, DigitalTwinState, BottleneckInfo, WhatIfResult
from .config import TYPES
import uuid

class Bridge:
    """Real Layer 4 protocol adapters, backed by the integrated runtime."""
    def __init__(self, runtime):
        self.runtime = runtime

    def get_state(self, mid):
        row = self.runtime.twin.get_machine_snapshot(mid)
        if not row:
            return None
        unavailable = row['stale'] or row['machine_status'] in ('DOWN', 'MAINTENANCE', 'UNKNOWN')
        status = MachineStatus.UNAVAILABLE if unavailable else (
            MachineStatus.FAULTED if row['fault_status'] == 'FAULT' else
            MachineStatus.IDLE if row['machine_status'] == 'IDLE' else MachineStatus.RUNNING)
        return MachineState(mid, TYPES[mid], status, production_rate=row['throughput_units_per_hour'])

    def find_candidates(self, compatible_types):
        # External mode has no verified standby/controller command integration.
        if self.runtime.settings.mode != 'demo':
            return []
        return [self.get_state(mid) for mid in self.runtime.flow.stations
                if TYPES[mid] in compatible_types and mid not in self.runtime.flow.routes.values()]

    def get_latest(self, mid):
        return None  # No trained failure-risk/health model was supplied.

    def get_twin_state(self, mid):
        row = self.runtime.twin.get_machine_snapshot(mid)
        if not row:
            return None
        return DigitalTwinState(mid, row['machine_status'], row['queue_length'], row['utilization'])

    def get_bottleneck_info(self, mid):
        ranked = self.runtime.ranking()
        return BottleneckInfo(ranked[0]['machine_id'] if ranked else None)

    def run_whatif(self, source, candidate):
        comparison = self.runtime.compare(source, 3600, 15, True)
        sid = 'SIM-' + uuid.uuid4().hex[:10]
        self.runtime.comparisons[sid] = comparison
        recovery = comparison.get('recovery')
        baseline = comparison['baseline']['throughput_units_per_hour']
        improved = bool(recovery and recovery['throughput_units_per_hour'] > baseline)
        # Apply the route only inside the demo, before the scheduler reports success.
        # This method executes under the runtime lock: simulation, validation and
        # commit cannot race with another decision/telemetry update.
        if improved:
            self.runtime.flow.reallocate(source, candidate)
            self.runtime.store.add('demo_route_applied', {'source':source,'candidate':candidate,'scenario_id':sid})
        delta = ((recovery['throughput_units_per_hour']-baseline)/baseline*100) if recovery and baseline else None
        return WhatIfResult(sid, source, candidate, improved, delta,
            'Finite-buffer demo simulation; route applied in the virtual line only.' if improved else
            'No compatible improvement was demonstrated; no allocation applied.')

    def notify_fault(self, machine_id, fault_type, deadline):
        self.runtime.store.add('operator_alert', dict(machine_id=machine_id,fault_type=fault_type,deadline=deadline))

    def notify_recovery_outcome(self, machine_id, summary):
        self.runtime.store.add('operator_outcome', dict(machine_id=machine_id,summary=summary))

