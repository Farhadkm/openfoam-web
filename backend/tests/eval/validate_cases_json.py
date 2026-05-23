"""Validate chatbot eval case JSON files. Run: python -m tests.eval.validate_cases_json [files...]"""

from __future__ import annotations

import sys
from pathlib import Path

from tests.eval.load_cases import CASES_DIR, DEFAULT_SUITE, CaseLoadError, load_cases


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if args:
        specs = args
    else:
        specs = [str(p) for p in sorted(CASES_DIR.glob("*.json"))]
        if not specs:
            specs = [DEFAULT_SUITE]

    errors: list[str] = []
    total = 0
    for spec in specs:
        try:
            cases = load_cases(spec)
            total += len(cases)
            print(f"OK {spec}: {len(cases)} case(s)")
        except CaseLoadError as exc:
            errors.append(f"{spec}: {exc}")

    if errors:
        for err in errors:
            print(f"FAIL {err}", file=sys.stderr)
        return 1
    print(f"Validated {len(specs)} file(s), {total} case(s) total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
