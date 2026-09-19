"""Bounded-buffer, deterministic flow used by the demo and isolated what-ifs.

Each board visits every logical stage. A standby substitutes at the same
logical position; it is never inserted as another mandatory production stage.
"""
from copy import deepcopy
from dataclasses import dataclass
from .config import TOPOLOGY

@dataclass
class Station:
    cycle: float
    capacity: float
    queue: int = 0
    active: bool = False
    remaining: float = 0
    completed: int = 0
    busy_seconds: float = 0
    downtime: float = 0
    status: str = 'IDLE'
    fault: str = 'NORMAL'
    down: bool = False

    @property
    def processing_time(self):
        return max(self.cycle, 3600 / self.capacity) if self.capacity > 0 else float('inf')

class Flow:
    def __init__(self, config, seed_wip=True):
        self.stations = {s.machine_id: Station(s.default_processing_time_sec, s.default_capacity_uph)
                         for s in config.machines}
        self.routes = {mid: mid for mid in TOPOLOGY}
        self.buffer_limit = 12
        self.arrival_interval = 3600 / 500
        self.arrival_progress = 0.0
        self.elapsed = 0.0
        self.finished = 0
        self.admitted = 0
        if seed_wip:
            for mid in TOPOLOGY:
                self.stations[mid].queue = 2
                self.admitted += 2

    def clone(self):
        return deepcopy(self)

    def reallocate(self, source, candidate):
        if source != 'M4' or candidate != 'M4-BACKUP' or candidate not in self.stations:
            raise ValueError('No configured compatible standby for this station')
        if self.routes[source] != source:
            raise ValueError('This operation already has an alternate route')
        src, dst = self.stations[source], self.stations[candidate]
        if dst.down or dst.fault != 'NORMAL' or dst.active or dst.queue:
            raise ValueError('Standby is not available')
        # Demo assumption: an interrupted test can restart in full on the standby.
        dst.queue += src.queue
        dst.active = src.active
        dst.remaining = dst.processing_time if src.active else 0
        src.queue, src.active, src.remaining = 0, False, 0
        self.routes[source] = candidate

    def step(self, seconds=1.0):
        if seconds < 0:
            raise ValueError('Time cannot move backwards')
        while seconds > 1e-9:
            dt = min(0.25, seconds)
            seconds -= dt
            self.elapsed += dt
            first = self.stations[self.routes['M1']]
            self.arrival_progress += dt
            if self.arrival_progress >= self.arrival_interval and first.queue < self.buffer_limit:
                first.queue += 1
                self.admitted += 1
                self.arrival_progress -= self.arrival_interval
            self.arrival_progress = min(self.arrival_progress, self.arrival_interval)
            for logical in reversed(TOPOLOGY):
                i = TOPOLOGY.index(logical)
                s = self.stations[self.routes[logical]]
                nxt = self.stations[self.routes[TOPOLOGY[i+1]]] if i < 4 else None
                if s.down or s.capacity <= 0:
                    s.status = 'DOWN'
                    s.downtime += dt
                    continue
                if not s.active and s.queue:
                    s.queue -= 1
                    s.active = True
                    s.remaining = s.processing_time
                if not s.active:
                    s.status = 'IDLE'
                    continue
                used = min(dt, s.remaining)
                s.busy_seconds += used
                s.remaining -= used
                s.status = 'RUNNING'
                if s.remaining <= 1e-9:
                    if nxt is not None and nxt.queue >= self.buffer_limit:
                        s.status = 'BLOCKED'
                    else:
                        s.active = False
                        s.completed += 1
                        if nxt is None:
                            self.finished += 1
                        else:
                            nxt.queue += 1
            for mid, station in self.stations.items():
                if mid not in self.routes.values():
                    station.status = 'DOWN' if station.down else 'IDLE'

    def wip(self):
        return sum(s.queue + int(s.active) for s in self.stations.values())

    def simulate(self, seconds, repair_after=None, repair_machine=None):
        initial = self.finished
        elapsed = 0.0
        repaired = False
        while elapsed < seconds:
            if repair_after is not None and not repaired and elapsed >= repair_after:
                s = self.stations[repair_machine]
                s.down = False
                repaired = True
            dt = min(1.0, seconds-elapsed)
            self.step(dt)
            elapsed += dt
        return {'finished_units': self.finished-initial,
                'throughput_units_per_hour': round((self.finished-initial)*3600/seconds, 2),
                'ending_wip': self.wip(),
                'ending_queues': {m:s.queue for m,s in self.stations.items()}}
