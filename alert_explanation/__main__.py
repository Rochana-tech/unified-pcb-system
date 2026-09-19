import argparse
import json
from pathlib import Path
from .models import AlertInput
from .service import explain_alert

def main():
    parser = argparse.ArgumentParser(description="Explain structured manufacturing evidence as JSON")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = AlertInput.model_validate_json(args.input.read_text(encoding="utf-8-sig"))
    rendered = explain_alert(payload).model_dump_json(indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)

if __name__ == "__main__":
    main()

