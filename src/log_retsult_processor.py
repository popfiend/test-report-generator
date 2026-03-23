import re
from typing import Dict, Tuple, List
from src.test_cast_dto import TestCase

class LogResultProcessor:
    LOG_RESULT_PATTERN = re.compile(
        r'TestResult\s*:\s*(?P<name>.+?)\s*\[(?P<status>pass|fail)\]',
        re.IGNORECASE
    )
    
    @classmethod
    def parse(cls, log_content: str) -> Dict[str, str]:
        results = {}
        if not log_content:
            return results
        
        for match in cls.LOG_RESULT_PATTERN.finditer(log_content):
            name = match.group('name').strip()
            status = match.group('status').strip().lower()
            if not name:
                continue
            if status == 'pass':
                results[name] = 'PASS'
            elif status == 'fail':
                results[name] = 'FAIL'
        return results
    
    @staticmethod
    def apply_to_cases(
        test_cases: List[TestCase],
        log_results: Dict[str, str],
    ) -> Tuple[int, Dict[str, str]]:
        if not log_results:
            return 0, {}
        
        case_map = {case.test_name: case for case in test_cases}
        applied = 0
        unmatched = {}
        
        for test_name, status in log_results.items():
            if test_name in case_map:
                case_map[test_name].result = status
                applied += 1
            else:
                unmatched[test_name] = status
        
        return applied, unmatched
