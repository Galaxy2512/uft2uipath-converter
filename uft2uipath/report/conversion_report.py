from dataclasses import dataclass, field

from uft2uipath.ast import ConversionIssue, ConversionStatus


@dataclass
class ConversionReport:
    project_name: str
    total_tests: int = 0
    success: int = 0
    partial: int = 0
    failed: int = 0
    unsupported: int = 0
    issues: list[ConversionIssue] = field(default_factory=list)

    def add_status(self, status: ConversionStatus) -> None:
        if status == ConversionStatus.SUCCESS:
            self.success += 1
        elif status == ConversionStatus.PARTIAL:
            self.partial += 1
        elif status == ConversionStatus.FAILED:
            self.failed += 1
        elif status == ConversionStatus.UNSUPPORTED:
            self.unsupported += 1

    @property
    def converted(self) -> int:
        return self.success + self.partial

    @property
    def success_rate(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return round((self.converted / self.total_tests) * 100, 2)