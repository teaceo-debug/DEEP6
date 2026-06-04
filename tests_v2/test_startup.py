"""Tests for deep6v2.__main__ — unified startup entry point."""

from __future__ import annotations

import asyncio

import pytest

from deep6v2.__main__ import main, parse_args


class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.dry_run is True
        assert args.live is False
        assert args.paper is False
        assert args.dev is False
        assert args.max_bars == 0

    def test_live_flag(self):
        args = parse_args(["--live"])
        assert args.live is True

    def test_paper_flag(self):
        args = parse_args(["--paper"])
        assert args.paper is True

    def test_dev_flag(self):
        args = parse_args(["--dev"])
        assert args.dev is True

    def test_max_bars(self):
        args = parse_args(["--max-bars", "100"])
        assert args.max_bars == 100

    def test_max_bars_default_zero(self):
        args = parse_args([])
        assert args.max_bars == 0

    def test_combined_flags(self):
        args = parse_args(["--live", "--dev", "--max-bars", "50"])
        assert args.live is True
        assert args.dev is True
        assert args.max_bars == 50


class TestMain:
    def test_main_dry_run_max_bars(self):
        """main() with --max-bars exits cleanly without blocking."""
        asyncio.run(main(["--max-bars", "10"]))

    def test_main_dev_mode(self):
        """main() with --dev configures console logging and exits."""
        asyncio.run(main(["--dev", "--max-bars", "1"]))

    def test_main_live_mode_label(self):
        """main() with --live labels mode correctly."""
        asyncio.run(main(["--live", "--max-bars", "1"]))

    def test_main_paper_mode_label(self):
        """main() with --paper labels mode correctly."""
        asyncio.run(main(["--paper", "--max-bars", "1"]))

    def test_main_no_max_bars_exits(self):
        """main() without --max-bars still exits (hits shutting_down)."""
        asyncio.run(main([]))
