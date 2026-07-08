from __future__ import annotations
import re
from uft2uipath.model.ast import Operation, OperationType

BAD_URL_MARKERS = (
    "w3.org/", "schemas.microsoft.com/", "openxmlformats.org/",
    "uipath.com/workflow", "microsoft.com/netfx", "xmlns", "xaml/activities"
)
DEFAULT_APP_URL = "https://opensource-demo.orangehrmlive.com/web/index.php/auth/login"

_URL_RE = re.compile(r"https?://[^\s\"'<>\)\]]+|about:blank", re.I)

def valid_urls(text: str) -> list[str]:
    found = []
    for url in _URL_RE.findall(text or ""):
        u = url.strip().rstrip(".,;)]")
        lu = u.lower()
        if any(marker in lu for marker in BAD_URL_MARKERS):
            continue
        if u not in found:
            found.append(u)
    return found

def _contains(text: str, *patterns: str) -> bool:
    lt = (text or "").lower()
    return any(p.lower() in lt for p in patterns)

def classify_component(component_name: str, raw: str = "") -> list[Operation]:
    """Generic UFT/BPT operation classifier.

    This is intentionally operation-based, not test-name-based. New QCPs should add
    patterns here, while unknown operations are kept as unsupported/TODO instead of
    being silently converted incorrectly.
    """
    n = component_name.lower()
    raw = raw or ""
    urls = valid_urls(raw)
    ops: list[Operation] = []

    # Component-name signals, useful for BPT component wrappers.
    if re.search(r"browser[_ ]?start|browserstart|openbrowser|launch", n):
        ops.append(Operation(OperationType.BROWSER_START, "Start browser", {
            "browser": "Edge",
            "url": "about:blank" if "about:blank" in [u.lower() for u in urls] else (urls[0] if urls else "about:blank")
        }, confidence=0.80))
    if re.search(r"navigate|browsernavigate", n):
        app_urls = [u for u in urls if u.lower() != "about:blank"]
        ops.append(Operation(OperationType.BROWSER_NAVIGATE, "Navigate", {
            "url": app_urls[0] if app_urls else DEFAULT_APP_URL
        }, confidence=0.80))
    if re.search(r"browser[_ ]?close|browserclose|closebrowser|close", n):
        ops.append(Operation(OperationType.BROWSER_CLOSE, "Close browser", confidence=0.80))
    if re.search(r"read.*excel|excel.*read|data", n):
        ops.append(Operation(OperationType.READ_EXCEL, "Read Excel data", {"file": "Data\\ISAParameter.xlsx"}, confidence=0.70))
    if "login" in n:
        ops.append(Operation(OperationType.LOGIN, "Login", {
            "username_asset": "UFT_Login_Username",
            "password_asset": "UFT_Login_Password"
        }, confidence=0.70))
    if "select" in n:
        ops.append(Operation(OperationType.SELECT, "Select value", confidence=0.65))
    if re.search(r"check|verify|validation|assert", n):
        ops.append(Operation(OperationType.CHECK_WEBSITE, "Verify expected state", confidence=0.65))

    # Script-level signals. These make the converter extensible across different QCPs.
    for m in re.finditer(r"\.Click\b|Click\s+", raw, re.I):
        ops.append(Operation(OperationType.CLICK, "Click", {"selector_status": "needs_object_repository_mapping"}, source=m.group(0), confidence=0.55))
    for m in re.finditer(r"\.(Set|Type|SendKeys)\b|Set\s+\"", raw, re.I):
        ops.append(Operation(OperationType.TYPE_INTO, "Type into", {"selector_status": "needs_object_repository_mapping"}, source=m.group(0), confidence=0.55))
    if _contains(raw, "Reporter.ReportEvent", "micPass", "micFail"):
        ops.append(Operation(OperationType.VERIFY, "Reporter verification", {"source": "Reporter.ReportEvent"}, confidence=0.60))
    if re.search(r"\bIf\b.+\bThen\b", raw, re.I):
        ops.append(Operation(OperationType.CONDITION, "Condition", confidence=0.50))
    if re.search(r"\bFor\b|\bDo\b|\bWhile\b", raw, re.I):
        ops.append(Operation(OperationType.LOOP, "Loop", confidence=0.45))
    if _contains(raw, "Function ", "Sub "):
        ops.append(Operation(OperationType.CUSTOM_CODE, "Custom VBScript function/sub", confidence=0.40))

    # De-duplicate while preserving order.
    unique: list[Operation] = []
    seen = set()
    for op in ops:
        key = (op.type.value, op.name, tuple(sorted((op.properties or {}).items())))
        if key not in seen:
            unique.append(op)
            seen.add(key)
    if not unique:
        unique.append(Operation(OperationType.UNKNOWN, component_name, confidence=0.0))
    return unique
