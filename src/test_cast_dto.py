from dataclasses import dataclass

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
    precondition: str = ""
    result: str = "Not Run"
    execution_time: float = 0.0
    
    @property
    def full_name(self) -> str:
        return f"{self.group_name}::{self.test_name}"