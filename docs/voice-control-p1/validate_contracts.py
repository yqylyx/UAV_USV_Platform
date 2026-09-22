"""Offline validation for the provider-neutral P1 contract artifacts."""
from pathlib import Path
import json
import re

from jsonschema import Draft7Validator, FormatChecker


ROOT = Path(__file__).resolve().parent


def main():
    schema = json.loads((ROOT / "contracts.schema.json").read_text(encoding="utf-8"))
    fixtures = json.loads((ROOT / "fixtures.json").read_text(encoding="utf-8"))
    Draft7Validator.check_schema(schema)
    definitions = schema["definitions"]
    seen = set()
    failures = []
    for case in fixtures["cases"]:
        assert case["id"] not in seen, f"duplicate fixture id: {case['id']}"
        seen.add(case["id"])
        assert case["definition"] in definitions, f"missing definition: {case['definition']}"
        selected = {
            "$schema": schema["$schema"],
            "$ref": f"#/definitions/{case['definition']}",
            "definitions": definitions,
        }
        errors = list(Draft7Validator(selected, format_checker=FormatChecker()).iter_errors(case["data"]))
        if (not errors) != case["valid"]:
            failures.append((case["id"], [error.message for error in errors]))
    assert not failures, f"fixture expectation failures: {failures}"

    contract = (ROOT / "interface-contract.md").read_text(encoding="utf-8")
    assert len(re.findall(r"^```", contract, re.MULTILINE)) % 2 == 0, "unbalanced markdown fences"
    assert "POST /api/voice/intelligence/transcriptions" in contract
    assert "POST /api/voice/intelligence/interpretations" in contract
    print(f"PASS: schema + {len(seen)} positive/negative P1 fixtures")
    print("No backend, provider, database, Python Runner or Unity connection was made.")


if __name__ == "__main__":
    main()
