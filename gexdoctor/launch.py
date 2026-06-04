from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

__all__ = ["main"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gexdoctor",
        description="GEX Doctor v0.1 - FlashAlpha to NQ Magnet Engine",
    )
    p.add_argument("--dry-run", action="store_true", help="Validate config and dependencies, then exit")
    p.add_argument("--once", action="store_true", help="Run one poll cycle, write JSON, then exit")
    p.add_argument("--interval", type=int, default=None, help="Override poll interval in seconds (minimum 15)")
    p.add_argument("--output", default=None, help="Override output JSON file path")
    p.add_argument("--verbose", "-v", action="store_true", help="Enable DEBUG logging")
    p.add_argument("--source", default=None, choices=["QQQ", "NDX"], help="FlashAlpha symbol to track (default: from config)")
    p.add_argument("--config", default="config.yaml", help="Path to config.yaml (default: config.yaml)")
    return p


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=level,
        force=True,
    )


def _build_overrides(args: argparse.Namespace) -> dict[str, object]:
    overrides: dict[str, object] = {}
    if args.interval is not None:
        overrides["interval"] = args.interval
    if args.output is not None:
        overrides["output_path"] = args.output
    if args.source is not None:
        overrides["source"] = args.source
    return overrides


def validate_config(config_path: Path, overrides: dict[str, object]) -> tuple[bool, list[str]]:
    """Validate config. Returns (is_valid, list_of_errors)."""
    try:
        from gexdoctor.monitor.config import GexDoctorConfig

        cfg = GexDoctorConfig.from_yaml(config_path, **overrides)
        missing = cfg.validate_required()
        if missing:
            return False, [f"Missing required env vars: {', '.join(missing)}"]
        return True, []
    except Exception as exc:
        return False, [str(exc)]


async def run_once(config_path: Path, overrides: dict[str, object]) -> int:
    """Run one poll cycle and write output. Return exit code."""
    try:
        from gexdoctor.monitor.adapters.flashalpha import FlashAlphaAdapter
        from gexdoctor.monitor.config import GexDoctorConfig
        from gexdoctor.monitor.interpreter import PositioningInterpreter
        from gexdoctor.monitor.magnet_scorer import MagnetScorer
        from gexdoctor.monitor.price_service import NQPriceService
        from gexdoctor.monitor.producer import GexDoctorProducer

        cfg = GexDoctorConfig.from_yaml(config_path, **overrides)
        output_path = Path(overrides.get("output_path", cfg.output_path))

        adapter = FlashAlphaAdapter(api_key=cfg.flashalpha_api_key, symbol=cfg.source)
        price_svc = NQPriceService(
            polygon_api_key=cfg.massive_api_key,
            flash_api_key=cfg.flashalpha_api_key,
        )
        scorer = MagnetScorer(
            min_confidence=cfg.min_confidence,
            anti_flicker_margin=cfg.anti_flicker_margin,
        )
        interpreter = PositioningInterpreter()

        producer = GexDoctorProducer(
            flashalpha_adapter=adapter,
            price_service=price_svc,
            scorer=scorer,
            interpreter=interpreter,
            output_path=output_path,
            log_dir=Path(cfg.log_dir),
            interval_sec=cfg.interval,
        )

        result = await producer.run_cycle()
        if result:
            print(f"GEX Doctor: cycle complete. Magnet={result.primary_magnet} Bias={result.bias_direction}")
            print(f"Output written to: {output_path}")
            return 0
        print("GEX Doctor: cycle completed with no magnet output")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


async def run_continuous(config_path: Path, overrides: dict[str, object]) -> int:
    """Run continuous polling loop."""
    try:
        from gexdoctor.monitor.adapters.flashalpha import FlashAlphaAdapter
        from gexdoctor.monitor.config import GexDoctorConfig
        from gexdoctor.monitor.interpreter import PositioningInterpreter
        from gexdoctor.monitor.magnet_scorer import MagnetScorer
        from gexdoctor.monitor.price_service import NQPriceService
        from gexdoctor.monitor.producer import GexDoctorProducer

        cfg = GexDoctorConfig.from_yaml(config_path, **overrides)
        output_path = Path(overrides.get("output_path", cfg.output_path))

        adapter = FlashAlphaAdapter(api_key=cfg.flashalpha_api_key, symbol=cfg.source)
        price_svc = NQPriceService(
            polygon_api_key=cfg.massive_api_key,
            flash_api_key=cfg.flashalpha_api_key,
        )
        scorer = MagnetScorer(
            min_confidence=cfg.min_confidence,
            anti_flicker_margin=cfg.anti_flicker_margin,
        )
        interpreter = PositioningInterpreter()

        producer = GexDoctorProducer(
            flashalpha_adapter=adapter,
            price_service=price_svc,
            scorer=scorer,
            interpreter=interpreter,
            output_path=output_path,
            log_dir=Path(cfg.log_dir),
            interval_sec=cfg.interval,
        )

        print("GEX Doctor v0.1 - FlashAlpha to NQ Magnet Engine")
        print(f"Output: {output_path}")
        print(f"Interval: {producer.interval_sec}s | Symbol: {cfg.source}")
        print("Press Ctrl+C to stop")

        await producer.run_loop()
        return 0
    except KeyboardInterrupt:
        print("\nGEX Doctor: stopped by user")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def main() -> int:
    """CLI entry point. Returns exit code."""
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.interval is not None and args.interval < 15:
        parser.error("--interval must be at least 15 seconds")

    config_path = Path(args.config)
    overrides = _build_overrides(args)

    if args.dry_run:
        valid, errors = validate_config(config_path, overrides)
        if valid:
            print("GEX Doctor: dry run OK - config valid")
            return 0
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    if args.once:
        return asyncio.run(run_once(config_path, overrides))

    return asyncio.run(run_continuous(config_path, overrides))


if __name__ == "__main__":
    sys.exit(main())
