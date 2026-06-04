"""CLI entry point."""
import argparse


def main():
    parser = argparse.ArgumentParser(description="Cross-Market AI Engine")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("live", help="Run live trading mode")
    sub.add_parser("shadow", help="Run shadow mode (no trading)")
    sub.add_parser("replay", help="Run historical replay")
    sub.add_parser("train", help="Train classifiers")
    sub.add_parser("dashboard", help="Start dashboard server")
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()


if __name__ == "__main__":
    main()
