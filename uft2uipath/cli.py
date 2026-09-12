import argparse
from pathlib import Path
from uft2uipath.archive.extractor import ArchiveExtractor
from uft2uipath.discovery.discovery_report import DiscoveryReportBuilder


def main():
    parser = argparse.ArgumentParser(
        prog="uft2uipath",
        description="UFT to UiPath Converter",
    )

    sub = parser.add_subparsers(dest="command")

    inspect_cmd = sub.add_parser(
        "inspect",
        help="Inspect an extracted UFT/ALM project folder",
    )
    inspect_cmd.add_argument("project")

    convert_cmd = sub.add_parser(
        "convert",
        help="Convert a UFT/ALM project to UiPath",
    )
    convert_cmd.add_argument("project")

    model_cmd = sub.add_parser("build-model", help="Build model from decoded ALM JSON")
    model_cmd.add_argument("source")
    model_cmd.add_argument("--out", required=True)

    args = parser.parse_args()

    if args.command == "build-model":
        from uft2uipath.rows_cli import main as build_model_main
        build_model_main([args.source, "--out", args.out])
    elif args.command == "inspect":
        _run_inspect(args.project)
    elif args.command == "convert":
        print(f"Converting: {args.project}")
    else:
        parser.print_help()


def _run_inspect(project_path: str) -> None:
    path = Path(project_path)

    if path.is_file() and path.suffix.lower() in [".qcp", ".zip"]:
        print(f"Extracting archive: {path}")
        path = ArchiveExtractor().extract(path)

    report = DiscoveryReportBuilder().build(path)

    print("===================================================")
    print("UFT Project Discovery Report")
    print("===================================================")
    print(f"Project root: {report.project_root}")
    print(f"Total files:  {report.total_files}")
    print()

    print("Categories:")
    for category, count in sorted(report.categories.items()):
        print(f"  {category}: {count}")

    print()
    print("XML files:")
    for xml in report.xml_files:
        print(f"  {xml.path.name}")
        print(f"    root: {xml.root_tag}")
        print(f"    elements: {xml.element_count}")


if __name__ == "__main__":
    main()
