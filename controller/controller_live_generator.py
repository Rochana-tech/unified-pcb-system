"""
Live Machine-Controller Telemetry Generator
============================================

Simulates the kind of data a PLC/MES (machine controller) actually
reports in real time -- production counters, cycle timing, batch info,
tool-change tracking, and fault/alarm codes -- rather than raw sensor
readings (temperature, torque, etc). This mirrors what you'd pull from
a controller over OPC-UA/Modbus/MQTT in a real factory.

Usage:
    python controller_live_generator.py
    python controller_live_generator.py --machines 4 --interval 0.5
    python controller_live_generator.py --out log.csv --limit 500
"""

import argparse
import csv
import json
import random
import time
from dataclasses import dataclass, field


@dataclass
class Machine:
    machine_id: str
    batch_id: str
    target_cycle_time: float          # seconds/unit, set by the job program
    units_produced_total: int = 0
    units_produced_batch: int = 0
    good_count: int = 0
    reject_count: int = 0
    cycle_count: int = 0
    units_since_tool_change: int = 0
    tool_change_count: int = 0
    downtime_seconds: float = 0.0
    state: str = "RUNNING"            # RUNNING / IDLE / FAULT / MAINTENANCE


def make_machine(index: int) -> Machine:
    return Machine(
        machine_id=f"M-{100 + index}",
        batch_id=f"BATCH-{random.randint(1000, 9999)}",
        target_cycle_time=round(random.uniform(8.0, 25.0), 1),
    )


TOOL_LIFE_UNITS = 2000          # controller's tool-change threshold (units between changes)
FAULT_CODES = {
    1: "JAM_DETECTED",
    2: "MOTOR_OVERLOAD",
    3: "POSITION_ERROR",
    4: "COMMS_TIMEOUT",
}


def generate_reading(m: Machine) -> dict:
    """One controller poll: advance production state and report current counters."""

    # Controller occasionally reports idle/maintenance/fault instead of a normal cycle
    roll = random.random()
    if roll < 0.03:
        m.state = "FAULT"
    elif roll < 0.06:
        m.state = "MAINTENANCE"
    elif roll < 0.10:
        m.state = "IDLE"
    else:
        m.state = "RUNNING"

    fault_code = 0
    cycle_time = None

    if m.state == "RUNNING":
        # actual cycle time drifts slightly, and drifts more as tool nears end of life
        wear_ratio = m.units_since_tool_change / TOOL_LIFE_UNITS
        drift = 1.0 + wear_ratio * 0.15
        cycle_time = round(m.target_cycle_time * drift * random.uniform(0.95, 1.05), 2)

        m.units_produced_total += 1
        m.units_produced_batch += 1
        m.cycle_count += 1
        m.units_since_tool_change += 1

        # quality: reject probability rises as tool wear increases
        reject_prob = 0.01 + wear_ratio * 0.04
        if random.random() < reject_prob:
            m.reject_count += 1
        else:
            m.good_count += 1

        # controller triggers a tool change once life threshold is hit
        if m.units_since_tool_change >= TOOL_LIFE_UNITS:
            m.units_since_tool_change = 0
            m.tool_change_count += 1

    elif m.state == "FAULT":
        fault_code = random.choice(list(FAULT_CODES))
        m.downtime_seconds += random.uniform(30, 300)

    elif m.state == "MAINTENANCE":
        m.downtime_seconds += random.uniform(300, 1800)

    elif m.state == "IDLE":
        m.downtime_seconds += random.uniform(5, 60)

    output_rate_per_hr = round(3600 / cycle_time, 1) if cycle_time else 0.0

    return {
        "timestamp": time.time(),
        "machine_id": m.machine_id,
        "batch_id": m.batch_id,
        "state": m.state,
        "fault_code": FAULT_CODES.get(fault_code, "NONE"),
        "cycle_count": m.cycle_count,
        "cycle_time_sec": cycle_time,
        "output_rate_per_hr": output_rate_per_hr,
        "units_produced_total": m.units_produced_total,
        "units_produced_batch": m.units_produced_batch,
        "good_count": m.good_count,
        "reject_count": m.reject_count,
        "units_since_tool_change": m.units_since_tool_change,
        "tool_change_count": m.tool_change_count,
        "downtime_seconds": round(m.downtime_seconds, 1),
    }


def live_stream(num_machines: int, interval: float):
    machines = [make_machine(i) for i in range(num_machines)]
    while True:
        m = random.choice(machines)
        yield generate_reading(m)
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="Live machine-controller data generator")
    parser.add_argument("--machines", type=int, default=3)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--out", type=str, default=None)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    stream = live_stream(args.machines, args.interval)
    f = open(args.out, "a", newline="") if args.out else None
    writer = None
    count = 0
    try:
        for reading in stream:
            if f:
                if writer is None:
                    writer = csv.DictWriter(f, fieldnames=reading.keys())
                    if f.tell() == 0:
                        writer.writeheader()
                writer.writerow(reading)
                f.flush()
            else:
                print(json.dumps(reading))
            count += 1
            if args.limit and count >= args.limit:
                break
    except KeyboardInterrupt:
        pass
    finally:
        if f:
            f.close()


if __name__ == "__main__":
    main()
