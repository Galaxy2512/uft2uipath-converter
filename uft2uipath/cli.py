import argparse


def main():
    parser = argparse.ArgumentParser(
        prog="uft2uipath",
        description="UFT to UiPath Converter",
    )

    sub = parser.add_subparsers(dest="command")

    inspect_cmd = sub.add_parser(
        "inspect",
        help="Inspect a QCP project",
    )

    inspect_cmd.add_argument(
        "project",
        help="Path to .qcp file or extracted project",
    )

    convert_cmd = sub.add_parser(
        "convert",
        help="Convert a project",
    )

    convert_cmd.add_argument("project")

    args = parser.parse_args()

    if args.command == "inspect":
        print(f"Inspecting: {args.project}")

    elif args.command == "convert":
        print(f"Converting: {args.project}")

    else:
        parser.print_help()