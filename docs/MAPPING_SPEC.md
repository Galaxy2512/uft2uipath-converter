\# UFT to UiPath Mapping Specification



\## Core Principle



No UFT information may be lost during conversion.



If an element cannot be fully converted, it must still appear in the generated UiPath project as one of:



\- TODO comment

\- Log Message

\- Manual Action placeholder

\- Unsupported Activity placeholder

\- Conversion report issue



\## Main Mapping



| UFT / ALM Element | UiPath Output |

|---|---|

| ALM Project / QCP | UiPath Test Automation Project |

| UFT Test | UiPath Test Case |

| Business Component | Reusable Workflow / XAML |

| Business Component Parameter | In / Out / InOut Argument |

| Local Variable | UiPath Variable |

| UFT Action / Step | UiPath Activity |

| Object Repository Item | UiPath Selector / Object Repository Item |

| DataTable | Excel file / Test Data |

| Condition | If activity |

| Loop | While / For Each activity |

| Checkpoint | Verify Expression / Verify Control Attribute |

| Reporter.ReportEvent | Log Message / Test Assertion |

| Function Library | UiPath Library / Invoked Workflow |

| Recovery Scenario | Try/Catch / Global Exception Handler |

| Unsupported Step | TODO + Manual Action placeholder |



\## Status Values



Each converted item must have one of:



\- SUCCESS

\- PARTIAL

\- FAILED

\- UNSUPPORTED



\## Unsupported Handling



Unsupported UFT elements must not be skipped.



They must be preserved with:



\- original UFT source

\- component name

\- test name

\- step name

\- reason

\- suggested UiPath mapping

