import re
import os
import sys

from typing import List
from src.test_cast_dto import TestCase
from src.vector_extractor import VectorExtractor

splite_line = 1024

class UnityTestParser:
    
    TEST_MACRO_PATTERN = re.compile(
        r'TEST\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)',
        re.MULTILINE
    )
    
    COMMENT_PATTERN = re.compile(
        r'//\s*@(\w+):\s*(.+?)(?=\n|$)',
        re.MULTILINE
    )
    
    def __init__(self, test_dir: str = "test", project_root: str = "."):
        self.test_dir = test_dir
        self.project_root = project_root
        self.test_cases: List[TestCase] = []
        self.vector_extractor = VectorExtractor(project_root)
    
    def _extract_comment_section(self, content: str, start_pos: int) -> str:
        comments: List[str] = []
        cursor = start_pos
        while cursor > 0:
            prev_newline = content.rfind('\n', 0, cursor - 1)
            line_start = 0 if prev_newline == -1 else prev_newline + 1
            line = content[line_start:cursor]
            stripped = line.strip()
            if not stripped.startswith('// @'):
                break
            comments.insert(0, line.strip('\r'))
            if prev_newline == -1:
                break
            cursor = prev_newline
        return '\n'.join(comments)
    
    def parse_file(self, file_path: str) -> List[TestCase]:
        cases = []
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            for match in self.TEST_MACRO_PATTERN.finditer(content):
                group_name = match.group(1)
                test_name = match.group(2)
                start_pos = match.start()
                line_num = content[:start_pos].count('\n') + 1
                
                comment_section = self._extract_comment_section(content, start_pos)
                
                fields = {}
                for comment_match in self.COMMENT_PATTERN.finditer(comment_section):
                    field_name = comment_match.group(1).lower()
                    field_value = comment_match.group(2).strip()
                    fields[field_name] = field_value
                
                description = fields.get('test_desc', test_name)
                given = fields.get('given', '-')
                expected = fields.get('expected', '-')
                precondition = fields.get('pre_con', '')
                test_id = fields.get('test_id', '')
                
                case = TestCase(
                    test_id=test_id,
                    file_path=file_path,
                    group_name=group_name,
                    test_name=test_name,
                    line_number=line_num,
                    description=description,
                    given_data=given,
                    expected_data=expected,
                    precondition=precondition
                )
                cases.append(case)
        
        except Exception as e:
            print(f"Error parsing {file_path}: {e}", file=sys.stderr)
        
        return cases
    
    def parse_all_tests(self) -> List[TestCase]:
        test_files = []
        
        for root, dirs, files in os.walk(self.test_dir):
            for file in files:
                if file.startswith('test_') and file.endswith('.c'):
                    test_files.append(os.path.join(root, file))
        
        for test_file in sorted(test_files):
            self.test_cases.extend(self.parse_file(test_file))
        
        return self.test_cases