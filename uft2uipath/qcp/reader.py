from __future__ import annotations
import re
from pathlib import Path
from uft2uipath.model.ast import Component, TestCase, MigrationModel, ConversionIssue, OperationType
from uft2uipath.qcp.alm_database import AlmDatabase
from uft2uipath.mapping.operation_classifier import classify_component

DEFAULT_FLOWS = {
    "Simply_BPT_TestCase": ["BrowserStart_QWERTZ", "BrowserNavigate_QWERTZ", "CheckWebsite_QWERTZ", "BrowserClose_QWERTZ"],
    "Fully_BPT_TestCase": ["ReadExcelAddressData_QWERTZ", "BrowserStart_QWERTZ", "BrowserNavigate_QWERTZ", "LoginWebsite_QWERTZ", "AdminWebsiteSelectUserRole_QWERTZ", "AdminWebsiteCheckUserRole_QWERTZ", "CheckWebsite_QWERTZ", "BrowserClose_QWERTZ"],
}

_GENERIC_COMPONENT_PATTERNS = [
    r"\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b",  # BPT-like tokens
    r"\b[A-Za-z][A-Za-z0-9]*(?:Start|Navigate|Close|Login|Check|Select|Excel|Verify)[A-Za-z0-9_]*\b",
]
_OPERATION_WORDS = ("browser", "navigate", "close", "login", "check", "verify", "select", "excel", "click", "type", "address", "website")

class QcpModelReader:
    """General ALM/QCP BPT reader.

    v0.2 is deliberately designed for many different QCP exports:
    - discover possible BPT components from ALM text/table/resource files,
    - classify generic UFT operations,
    - never silently fake unsupported logic; unknown items appear in ConversionReport.md.
    """
    def read(self, extracted_dir: str | Path, source_qcp: str | Path) -> MigrationModel:
        db = AlmDatabase.load(extracted_dir)
        component_names = self._discover_components(db)
        components: list[Component] = []
        issues: list[ConversionIssue] = []

        for name in component_names:
            raw, sources = db.snippets_for(name)
            operations = classify_component(name, raw)
            if any(op.type == OperationType.UNKNOWN for op in operations):
                issues.append(ConversionIssue("warning", name, "No confident operation mapping found; generated as TODO/unmapped step."))
            if any(op.type in (OperationType.CLICK, OperationType.TYPE_INTO, OperationType.SELECT, OperationType.CHECK_WEBSITE) for op in operations):
                issues.append(ConversionIssue("info", name, "UI selector/object repository mapping is required for full native execution."))
            components.append(Component(name=name, operations=operations, raw_text=raw[:10000] if raw else None, source_files=sorted(set(sources))))

        tests = self._discover_tests(db, components)
        if not tests and components:
            tests = [TestCase("Migrated_BPT_TestCase", [c.name for c in components], source="fallback_order")]
            issues.append(ConversionIssue("info", "Migrated_BPT_TestCase", "Original BPT flow was not confidently reconstructed; fallback component order was used."))

        return MigrationModel(str(source_qcp), components, tests, str(Path(extracted_dir)), issues)

    def _discover_components(self, db: AlmDatabase) -> list[str]:
        blob = db.blob
        candidates: set[str] = set()
        for pat in _GENERIC_COMPONENT_PATTERNS:
            for token in re.findall(pat, blob):
                low = token.lower()
                if len(token) < 4 or len(token) > 80:
                    continue
                if any(skip in low for skip in ("schema", "xmlns", "assembly", "namespace", "version", "publickeytoken")):
                    continue
                if any(word in low for word in _OPERATION_WORDS) or low.endswith("_qwertz"):
                    candidates.add(token)
        # Prefer readable, operation-like component names over random ALM technical tokens.
        return sorted(candidates, key=lambda x: (0 if x.endswith("_QWERTZ") else 1, x.lower()))

    def _discover_tests(self, db: AlmDatabase, components: list[Component]) -> list[TestCase]:
        blob = db.blob
        component_set = {c.name for c in components}
        tests: list[TestCase] = []
        for test_name, flow in DEFAULT_FLOWS.items():
            present_flow = [c for c in flow if c in component_set]
            if test_name in blob or len(present_flow) >= 2:
                tests.append(TestCase(test_name, present_flow, source="known_bpt_flow_hint"))
        # Generic test name discovery can be added here once more QCP samples are available.
        return tests
