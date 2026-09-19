"""
Live scoring: consumes the controller stream, builds rolling features per
machine, and reports failure probability + anomaly flag on every cycle.

Run (after train_models.py has produced the .joblib files):
    python predict_live.py --machines 3 --interval 0.2
"""

import argparse
import random
import time

import joblib

from controller.controller_live_generator import make_machine, generate_reading
from controller.feature_engineering import MachineFeatureBuilder, FEATURE_NAMES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--machines", type=int, default=3)
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    clf = joblib.load("failure_model.joblib")
    iso = joblib.load("anomaly_model.joblib")

    machines = [make_machine(i) for i in range(args.machines)]
    builders = {m.machine_id: MachineFeatureBuilder() for m in machines}

    count = 0
    while True:
        m = random.choice(machines)
        reading = generate_reading(m)
        feats = builders[m.machine_id].update(reading)
        x = [[feats[name] for name in FEATURE_NAMES]]

        fail_prob = clf.predict_proba(x)[0][1]
        is_anomaly = iso.predict(x)[0] == -1   # -1 = anomaly, 1 = normal

        flag = ""
        if is_anomaly:
            flag += " [ANOMALY]"
        if fail_prob > 0.5:
            flag += f" [FAILURE RISK {fail_prob:.0%}]"

        print(
            f"{m.machine_id} | state={reading['state']:<11} "
            f"cycle_time={reading['cycle_time_sec']} "
            f"fail_prob={fail_prob:.2f}{flag}"
        )

        count += 1
        if args.limit and count >= args.limit:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
