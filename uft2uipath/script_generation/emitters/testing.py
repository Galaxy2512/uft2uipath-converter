"""Test outcome: reported results and ending the test."""
import xml.etree.ElementTree as ET

from uft2uipath.script_generation.emitter import (
    EXIT_FAILED_SUFFIX, EXIT_TEST_MARKER, UI, assign, expr, literal, q,
)
from uft2uipath.script_generation.handlers import emits


# Reporter status (constant or its numeric value) -> log level and label.
REPORT_LEVELS = {
    "micpass": ("Info", "PASS"), "0": ("Info", "PASS"),
    "micfail": ("Error", "FAIL"), "1": ("Error", "FAIL"),
    "micdone": ("Info", "DONE"), "2": ("Info", "DONE"),
    "micwarning": ("Warn", "WARNING"), "3": ("Warn", "WARNING"),
}


@emits("ReportEventOperation")
def emit_report_event(ctx, node, parent, trace, display):
    """Reporter.ReportEvent: Log Message with the level of the status.

    micFail also sets the InOut failure flag, so execution continues as in UFT
    and the calling test fails at its end.
    """
    status = (node.get("status") or "").strip()
    if status.lower() not in REPORT_LEVELS:
        raise ValueError(f"Reporter status {status!r} needs interpretation.")
    level, label = REPORT_LEVELS[status.lower()]
    title = ctx.value(node.get("title"), "String", parent)
    details = ctx.value(node.get("message"), "String", parent)
    message = f"{literal(f'[{label}] ')} + {title} + {literal(': ')} + {details}"
    ET.SubElement(parent, q("LogMessage", UI), {
        "DisplayName": display, "Level": level, "Message": expr(message),
    })
    if label != "FAIL":
        trace.update(status="mapped_unverified", activity=f"LogMessage ({level})")
        return
    assign(parent, display + " / mark test failed", ctx.failure_flag(), "Boolean", "true")
    trace.update(status="mapped_unverified", activity="LogMessage (Error) + Assign",
                 note="Execution continues as in UFT; the calling test fails at its end.")


@emits("ExitTestOperation")
def emit_exit_test(ctx, node, parent, trace, display):
    """ExitTest: throw the marked exception the calling test catches.

    The message says whether a failure was reported before, because a
    faulted workflow does not return its InOut arguments.
    """
    code = (node.get("code") or {}).get("raw", "")
    ctx.exits_test = True
    # A faulted workflow does not hand back its InOut arguments, so the
    # failure flag travels in the message for the calling test to read.
    flag = ctx.failure_flag()
    message = literal(f"{EXIT_TEST_MARKER} UFT ExitTest({code}) in {ctx.component_id}, "
                      f"line {node.get('line_number')}")
    ET.SubElement(parent, q("Throw"), {
        "DisplayName": display,
        "Exception": expr(f"new System.ApplicationException({message} + "
                          f"({flag} ? {literal(EXIT_FAILED_SUFFIX)} : {literal('')}))"),
    })
    trace.update(status="mapped_unverified", activity="Throw (ExitTest)",
                 note="Stops the test; the outcome follows the failures reported before it.")
