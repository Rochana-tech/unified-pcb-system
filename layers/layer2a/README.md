# Layer 2A — ANN Fault Detection

Scope: **only** "what fault is occurring in this machine right now?" —
a genuine, backprop-trained artificial neural network (not if/else
thresholds) that classifies a sensor reading into a fault type.

Explicitly NOT built here (per project scope): health scoring, digital
twin, bottleneck detection, what-if simulation, recovery planning, AI
explanation, dashboard, developer workspace.

## Why scikit-learn's MLPClassifier instead of PyTorch/TensorFlow

This container ran out of disk space installing PyTorch's full CUDA
dependency stack (~1GB+ for a 4-feature/4-class prototype). `MLPClassifier`
is a real multi-layer perceptron — weighted layers, ReLU activations, Adam
optimizer, trained via backpropagation — so it satisfies "must actually be
trained" while being lightweight, dependency-light, and having built-in
`predict_proba` and simple `joblib` save/load. Swapping to PyTorch later
only touches `model/architecture.py`; nothing else in the pipeline depends
on the framework choice.

## Layout

```
config/               industry configs (feature order, fault classes, severity rules, artifact paths)
  industry_config.py    registry: load_industry_config(), require_trained_config()
  electronics_pcb.yaml  trained
  automobile.yaml        placeholder — status: not_trained, refuses inference (no silent fallback)

data/
  generate_synthetic.py  synthetic training data per fault class (distinct distributions + noise)
  datasets/               generated CSVs land here

preprocessing/
  scaler.py              fit/save/load StandardScaler — fit on train split only

model/
  architecture.py        build_ann() — the MLP definition, swap frameworks here later
  train.py               full pipeline: load -> split -> scale -> train -> evaluate -> save
  evaluate.py             accuracy / macro precision & recall / confusion matrix

inference/
  fault_event.py          FaultEvent schema + config-driven severity rule (not ML)
  predictor.py             FaultPredictor — loads model+scaler, reading -> FaultEvent

interface/
  layer1_adapter.py       handle_reading()/handle_batch() — the only file that changes
                            when Layer 1's real transport (queue/socket/REST) is decided

tests/
  test_inference.py       tests the predictor with zero dashboard/Layer-1 dependency

saved_models/<industry>/  model.joblib, scaler.joblib, metadata.json (metrics + training info)
```

## Running it

```bash
# 1. Generate synthetic training data (swap for real sensor data later — same schema)
python -m data.generate_synthetic --industry electronics_pcb --n-per-class 1000

# 2. Train (prints validation + held-out test metrics, saves artifacts)
python -m model.train --industry electronics_pcb

# 3. Test the predictor independently of any dashboard
python tests/test_inference.py

# 4. Use it, e.g. from the Layer 1 adapter:
python -c "
from interface.layer1_adapter import handle_reading
event = handle_reading({
    'machine_id': 'PCB-LINE-02', 'timestamp': '2026-09-19T10:00:05Z',
    'current': 12.4, 'temperature': 61.0, 'vibration': 1.2, 'rpm': 1380,
})
print(event.as_dict())
"
```

## Current model performance (synthetic data, electronics_pcb)

Test-set accuracy ~98.5%, macro precision/recall ~0.98 — see
`saved_models/electronics_pcb/metadata.json` for the full report
(this will change whenever real sensor data replaces the synthetic set).

## Adding a new industry

1. Copy `config/electronics_pcb.yaml` to `config/<industry>.yaml`, set
   `status: not_trained`, adjust `fault_classes`/`severity_rules` if needed.
2. Generate or supply a dataset at `data/datasets/<industry>_synthetic.csv`
   with the same feature + `fault_type` columns.
3. Run `python -m model.train --industry <industry>` — this flips the
   config to usable once you also set `status: trained` in the yaml.
4. No other code changes needed — `FaultPredictor("<industry>")` and the
   Layer 1 adapter both pick it up automatically.

## Known limitation

`config/industry_config.py` reads `status: trained` from the YAML as a
manual flag (set by whoever runs training). It doesn't yet auto-flip to
`trained` when `model/train.py` finishes — that's a one-line edit to the
yaml today, worth automating once a real integration layer exists.


## Simple UI (presentation only)

A standalone browser UI is included in `frontend/`. It shows the trained Layer 2A model information, sensor features, supported fault classes, and a preview/download of the bundled electronics dataset. It does **not** connect to Layer 1 or run inference from the browser.

Run from the project root:

```bash
run_ui.bat
```

Then open `http://localhost:5174`.
