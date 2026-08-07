"""Command-line interface: options_strategy qa|run|sweep|match|report."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from options_strategy import __version__

_NOT_YET = {
    "qa": "P0",
    "run": "P2",
    "sweep": "P4",
    "match": "P6",
    "report": "P6",
}


def _stub(command: str) -> int:
    print(
        f"options_strategy {command}: not implemented yet (arrives in {_NOT_YET[command]})",
        file=sys.stderr,
    )
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="options_strategy",
        description=(
            "SPX weekly double-diagonal research backtester. "
            "Research software only — not investment advice."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("qa", help="run the data QA gate on a dataset (PLAN §4.2)")
    sub.add_parser("run", help="run a single backtest from a config")
    sub.add_parser("sweep", help="run a parameter sweep from a space definition")
    sub.add_parser("match", help="ABC fingerprint matching against targets")
    sub.add_parser("report", help="render the report for a ledger run")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return _stub(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
