"""Debug-only console output, gated behind the --Debug/-d CLI flag."""

import argparse


def debug_print(args: argparse.Namespace, *msg: object) -> None:
    """Print `msg` prefixed with '[Debug]' only when args.Debug is set."""
    if args.Debug:
        print('[Debug]', *msg)
