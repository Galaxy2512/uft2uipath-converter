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

    rows_cmd = sub.add_parser("convert-rows", help="Generate review scaffold from decoded ALM JSON")
    rows_cmd.add_argument("source")
    rows_cmd.add_argument("--out", required=True)

    scripts_cmd = sub.add_parser("analyze-scripts", help="Analyze UFT scripts by component ID")
    scripts_cmd.add_argument("manifest")
    scripts_cmd.add_argument("--out", required=True)
    scripts_cmd.add_argument("--fail-on-blockers", action="store_true")

    args = parser.parse_args()

    if args.command == "analyze-scripts":
        from uft2uipath.script_analysis.batch import main as scripts_main
        options = [args.manifest, "--out", args.out]
        if args.fail_on_blockers:
            options.append("--fail-on-blockers")
        scripts_main(options)
    elif args.command == "convert-rows":
        from uft2uipath.convert_rows import main as convert_rows_main
        convert_rows_main([args.source, "--out", args.out])
    elif args.command == "build-model":
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
