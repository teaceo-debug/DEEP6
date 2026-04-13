"""DEEP6 v2.0 — async entry point with uvloop.

Uses Python 3.12 asyncio.Runner with loop_factory (not deprecated uvloop.install()).
Per D-13: asyncio event loop with uvloop drives all I/O and signal computation.
"""
import asyncio
import uvloop

from deep6.config import Config


async def main(config: Config) -> None:
    """Main asyncio coroutine. Builds shared state, connects Rithmic, gathers tasks.

    Tasks assembled in Plans 02-04. Placeholder gather for bootstrap.
    """
    import structlog
    log = structlog.get_logger()
    log.info("deep6.starting", version="2.0.0")
    # Per D-16: GC management at session boundaries is handled in SessionManager (Plan 03)
    # Tasks assembled in later plans; placeholder gather for now
    await asyncio.gather()


def cli_entry() -> None:
    """CLI entry point registered in pyproject.toml [project.scripts]."""
    config = Config.from_env()
    with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
        runner.run(main(config))


if __name__ == "__main__":
    cli_entry()
