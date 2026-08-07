"""Command-line interface: options_strategy qa|worldgen|run|sweep|match|report."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from options_strategy import __version__

_NOT_YET = {
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


def _cmd_worldgen(args: argparse.Namespace) -> int:
    from options_strategy import ledger
    from options_strategy.config import config_hash, load_config
    from options_strategy.data.synthetic.config import SyntheticWorldConfig
    from options_strategy.data.synthetic.world import generate_world

    cfg = load_config(args.config, SyntheticWorldConfig)
    paths, summary = generate_world(cfg, args.out)
    print(f"world '{cfg.name}' -> {paths.root} ({summary['n_quote_rows']:,} quote rows)")
    if not args.no_ledger:
        ledger.append(
            [
                ledger.LedgerRow(
                    kind="worldgen",
                    config_hash=config_hash(cfg),
                    git_sha=ledger.current_git_sha(),
                    data_version=cfg.data_version,
                    seed=cfg.seed,
                    metrics={k: int(v) for k, v in summary.items()},
                    artifacts=[str(paths.manifest)],
                )
            ],
            args.ledger,
        )
    return 0


def _cmd_qa(args: argparse.Namespace) -> int:
    from options_strategy import ledger
    from options_strategy.config import config_hash, load_config
    from options_strategy.data.qa import QAConfig, run_qa

    qa_cfg = load_config(args.config, QAConfig) if args.config else QAConfig()
    result = run_qa(args.world, qa_cfg)
    verdict = "CLEAN" if result.clean else "NOT CLEAN"
    print(f"QA verdict: {verdict}")
    print(f"report: {result.report_path}")
    if not args.no_ledger:
        manifest = json.loads((Path(args.world) / "manifest.json").read_text())
        ledger.append(
            [
                ledger.LedgerRow(
                    kind="qa",
                    config_hash=config_hash(qa_cfg),
                    git_sha=ledger.current_git_sha(),
                    data_version=result.summary["data_version"],
                    seed=int(manifest.get("config", {}).get("seed", 0)),
                    metrics=result.summary,
                    artifacts=[str(result.report_path), str(result.flags_path)],
                )
            ],
            args.ledger,
        )
    return 0 if result.clean else 1


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

    p_worldgen = sub.add_parser("worldgen", help="generate a SYNTHETIC world from a config")
    p_worldgen.add_argument("--config", required=True, help="SyntheticWorldConfig YAML")
    p_worldgen.add_argument("--out", default="data/synthetic/worlds", help="output root")
    p_worldgen.add_argument("--ledger", default="experiments/ledger.parquet")
    p_worldgen.add_argument("--no-ledger", action="store_true")
    p_worldgen.set_defaults(func=_cmd_worldgen)

    p_qa = sub.add_parser("qa", help="run the data QA gate on a dataset (PLAN §4.2)")
    p_qa.add_argument("--world", required=True, help="dataset root (contains manifest.json)")
    p_qa.add_argument("--config", default=None, help="QAConfig YAML (defaults otherwise)")
    p_qa.add_argument("--ledger", default="experiments/ledger.parquet")
    p_qa.add_argument("--no-ledger", action="store_true")
    p_qa.set_defaults(func=_cmd_qa)

    for name in _NOT_YET:
        p = sub.add_parser(name, help=f"(arrives in {_NOT_YET[name]})")
        p.set_defaults(func=None, stub_name=name)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "func", None) is None:
        return _stub(args.stub_name)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
