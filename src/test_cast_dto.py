from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class TestCase:
    test_id: str
    file_path: str
    group_name: str
    test_name: str
    line_number: int
    description: str
    given_data: str
    expected_data: str
    actual_data: str = "-"
    precondition: str = ""
    result: str = "Not Run"
    execution_time: float = 0.0
    # 실행 로그 TestLog 줄 (순서 보존). 비어 있으면 소스 주석 Given/Expected/Actual 사용.
    log_entries: List[Any] = field(default_factory=list)
    
    @property
    def full_name(self) -> str:
        return f"{self.group_name}::{self.test_name}"