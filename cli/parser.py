"""Command Line Argument Parser for Windows Power Explorer (REQ-15)."""

import argparse
import sys
from typing import Sequence

from core.__version__ import __version__
from core.power_manager import PowerManager
from cli.commands import (
    cmd_edit_setting,
    cmd_list_schemes,
    cmd_list_settings,
    cmd_reset_setting,
    cmd_show_setting,
    emit_error,
    EXIT_ERR_GENERAL,
    EXIT_SUCCESS,
)


def create_parser() -> argparse.ArgumentParser:
    """Construct the main CLI parser with global flags and subcommands."""
    # Common parent parser for flags valid globally
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument("--json", "-j", action="store_true", default=argparse.SUPPRESS, help="Emit structured JSON output")
    common_parser.add_argument("--verbose", "-v", action="store_true", default=argparse.SUPPRESS, help="Enable verbose debug logging")
    common_parser.add_argument("--dry-run", "-n", action="store_true", default=argparse.SUPPRESS, help="Simulate mutation without writing")
    common_parser.add_argument("--yes", "-y", action="store_true", default=argparse.SUPPRESS, help="Assume yes for non-destructive prompts")

    parser = argparse.ArgumentParser(
        prog="WindowsPowerExplorer.exe",
        description=f"Windows Power Explorer {__version__} - CLI",
        parents=[common_parser],
    )
    parser.add_argument("--version", "-V", action="version", version=f"Windows Power Explorer {__version__}")

    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # list-schemes
    subparsers.add_parser("list-schemes", parents=[common_parser], help="List all available power schemes")

    # list-settings
    p_list_set = subparsers.add_parser("list-settings", parents=[common_parser], help="List power settings")
    p_list_set.add_argument("--scheme", "-s", type=str, default=None, help="Scheme GUID or friendly name")
    p_list_set.add_argument("--category", "-c", type=str, default=None, help="Filter by subgroup category")
    p_list_set.add_argument("--search", "-q", type=str, default=None, help="Filter by query string")
    p_list_set.add_argument("--modified-only", "-m", action="store_true", help="Show only modified settings")
    p_list_set.add_argument("--hidden-only", action="store_true", help="Show only hidden settings")

    # show-setting
    p_show_set = subparsers.add_parser("show-setting", parents=[common_parser], help="Show details of a specific setting")
    p_show_set.add_argument("--setting", type=str, required=True, help="Setting GUID")
    p_show_set.add_argument("--scheme", "-s", type=str, default=None, help="Scheme GUID or friendly name")

    # edit-setting
    p_edit_set = subparsers.add_parser("edit-setting", parents=[common_parser], help="Edit AC and/or DC value for a setting")
    p_edit_set.add_argument("--setting", type=str, required=True, help="Setting GUID")
    p_edit_set.add_argument("--scheme", "-s", type=str, default=None, help="Scheme GUID or friendly name")
    p_edit_set.add_argument("--ac", type=int, default=None, help="New AC (plugged-in) value")
    p_edit_set.add_argument("--dc", type=int, default=None, help="New DC (battery) value")

    # reset-setting
    p_reset_set = subparsers.add_parser("reset-setting", parents=[common_parser], help="Reset setting value to default")
    p_reset_set.add_argument("--setting", type=str, required=True, help="Setting GUID")
    p_reset_set.add_argument("--scheme", "-s", type=str, default=None, help="Scheme GUID or friendly name")
    p_reset_set.add_argument("--ac", action="store_true", help="Reset AC value only")
    p_reset_set.add_argument("--dc", action="store_true", help="Reset DC value only")

    return parser


def parse_and_dispatch(argv: Sequence[str] | None = None, pm: PowerManager | None = None) -> int:
    """Parse CLI arguments and dispatch to the corresponding subcommand handler."""
    if argv is None:
        argv = sys.argv[1:]

    parser = create_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EXIT_SUCCESS

    # Coerce tri-state boolean flags
    args.json = bool(getattr(args, "json", False))
    args.verbose = bool(getattr(args, "verbose", False))
    args.dry_run = bool(getattr(args, "dry_run", False))
    args.yes = bool(getattr(args, "yes", False))

    if not args.subcommand:
        parser.print_help()
        return EXIT_SUCCESS

    if pm is None:
        pm = PowerManager()

    try:
        if args.subcommand == "list-schemes":
            return cmd_list_schemes(args, pm)
        elif args.subcommand == "list-settings":
            return cmd_list_settings(args, pm)
        elif args.subcommand == "show-setting":
            return cmd_show_setting(args, pm)
        elif args.subcommand == "edit-setting":
            return cmd_edit_setting(args, pm)
        elif args.subcommand == "reset-setting":
            return cmd_reset_setting(args, pm)
        else:
            return emit_error("ERR_GENERAL", EXIT_ERR_GENERAL, f"Unknown subcommand: {args.subcommand}", getattr(args, "json", False))
    except Exception as exc:
        return emit_error("ERR_GENERAL", EXIT_ERR_GENERAL, str(exc), getattr(args, "json", False))
