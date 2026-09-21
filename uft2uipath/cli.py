# Command-line entry point for the uft2uipath converter. Wires up subcommands
# (inspect, convert, inventory, build-model, convert-rows, analyze-scripts,
# emit-workflows, migrate-project) that drive the extraction, ALM decoding,
# script analysis and UiPath project/workflow generation stages. `convert` is
# the end-to-end command; `inventory` summarizes coverage of convert outputs.
import argparse
from pathlib import Path
from uft2uipath.archive.extractor import ArchiveExtractor
from uft2uipath.discovery.discovery_report import DiscoveryReportBuilder
from uft2uipath.script_generation.browser_scopes import BROWSER_TYPES


def main():
    """Parse the command line and run the chosen subcommand."""
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
        help="Run the conversion pipeline on a .qcp/.zip export or extracted folder",
    )
    convert_cmd.add_argument("project")
    convert_cmd.add_argument("--out", required=True, help="New output directory")
    convert_cmd.add_argument("--test-id", type=int, action="append", dest="test_ids",
                             help="ALM TS_TEST_ID to convert; repeat for several (default: all)")
    convert_cmd.add_argument("--accept-selectors", type=float, metavar="MIN_CONFIDENCE",
                             help="Generate with selector candidates at or above this confidence (0-1)")
    convert_cmd.add_argument("--selector-review", metavar="FILE",
                             help="Review file whose accepted selectors are used (see selector-review.template.json)")
    convert_cmd.add_argument("--browser-type", choices=sorted(BROWSER_TYPES),
                             help="Browser the generated web activities attach to")
    convert_cmd.add_argument("--timeout-ms", type=int, default=30000,
                             help="Activity timeout in milliseconds (default: 30000)")

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

    emit_cmd = sub.add_parser("emit-workflows", help="Generate workflow candidates from script analysis")
    emit_cmd.add_argument("analysis")
    emit_cmd.add_argument("--bindings", required=True)
    emit_cmd.add_argument("--out", required=True)

    project_cmd = sub.add_parser("migrate-project", help="Generate a complete UiPath test project")
    project_cmd.add_argument("manifest")
    project_cmd.add_argument("--bindings", required=True)
    project_cmd.add_argument("--out", required=True)
    project_cmd.add_argument("--project-template")
    project_cmd.add_argument("--zip", action="store_true")

    inventory_cmd = sub.add_parser("inventory", help="Count UFT operations, blockers and coverage")
    inventory_cmd.add_argument("reports", nargs="+", help="convert output directories or generation-report.json files")
    inventory_cmd.add_argument("--out", help="Also write the inventory as JSON")

    args = parser.parse_args()

    if args.command == "inventory":
        from uft2uipath.mapping.inventory import main as inventory_main
        inventory_main([*args.reports, *(["--out", args.out] if args.out else [])])
    elif args.command == "migrate-project":
        from uft2uipath.script_generation.project import main as project_main
        options = [args.manifest, "--bindings", args.bindings, "--out", args.out]
        if args.project_template:
            options.extend(["--project-template", args.project_template])
        if args.zip:
            options.append("--zip")
        project_main(options)
    elif args.command == "emit-workflows":
        from uft2uipath.script_generation.batch import main as emit_main
        emit_main([args.analysis, "--bindings", args.bindings, "--out", args.out])
    elif args.command == "analyze-scripts":
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
        _run_convert(parser, args)
    else:
        parser.print_help()


def _run_convert(parser, args) -> None:
    """The convert command: run ConversionPipeline and print where its artifacts are."""
    import json

    from uft2uipath.mapping.acceptance import AcceptanceSettings, load_review
    from uft2uipath.pipeline import PENDING_STAGES, ConversionPipeline

    if args.accept_selectors is not None and not 0 <= args.accept_selectors <= 1:
        parser.error("--accept-selectors takes a confidence between 0 and 1.")
    review = {}
    if args.selector_review:
        try:
            review = load_review(json.loads(Path(args.selector_review).read_text(encoding="utf-8-sig")))
        except (OSError, ValueError) as exc:
            parser.error(f"--selector-review: {exc}")
    acceptance = AcceptanceSettings(
        threshold=args.accept_selectors, browser_type=args.browser_type,
        timeout_ms=args.timeout_ms, review=review,
    )

    try:
        result = ConversionPipeline(args.project, args.out, args.test_ids, acceptance).run()
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Project: {result.project.name}")
    print(f"Tests selected: {len(result.project.tests)}")
    for name, path in result.artifacts.items():
        print(f"  {name}: {path}")
    if result.table_errors:
        print(f"Tables that failed to decode: {', '.join(sorted(result.table_errors))}")
    print(f"Not yet implemented: {', '.join(PENDING_STAGES)}.")
    print("Static Studio-project validation runs automatically.")
    print("Actual Studio load, execution and UFT equivalence are unverified.")


def _run_inspect(project_path: str) -> None:
    """The inspect command: print a discovery report of an extracted project or archive."""
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
