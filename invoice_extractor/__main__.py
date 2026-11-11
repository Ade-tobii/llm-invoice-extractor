"""CLI: python -m invoice_extractor samples/northwind_supplies.txt [--demo]"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from invoice_extractor.extractors import FakeExtractor, GeminiExtractor
from invoice_extractor.graph import process_invoice

DEMO_DIR = Path(__file__).resolve().parent.parent / "samples" / "demo_responses"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="invoice_extractor", description=__doc__)
    parser.add_argument("invoice", type=Path, help="path to an invoice as plain text or markdown")
    parser.add_argument("--demo", action="store_true",
                        help="replay recorded model responses instead of calling Gemini")
    parser.add_argument("--max-retries", type=int, default=1)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stderr)

    if args.demo:
        script = DEMO_DIR / f"{args.invoice.stem}.json"
        if not script.exists():
            parser.error(f"no demo responses for {args.invoice.name} (expected {script})")
        extractor = FakeExtractor.from_file(script)
    else:
        extractor = GeminiExtractor()

    text = args.invoice.read_text(encoding="utf-8")
    result = process_invoice(text, extractor, max_retries=args.max_retries)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "done" else 2


if __name__ == "__main__":
    sys.exit(main())
