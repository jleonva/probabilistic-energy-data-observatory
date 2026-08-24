from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Probabilistic Energy Data Observatory")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Run ingestion, checks, modelling and reporting")
    run_parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args()
    if args.command == "run":
        print(json.dumps(run(args.root), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

