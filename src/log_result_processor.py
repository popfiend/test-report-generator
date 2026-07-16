import re
from dataclasses import dataclass, field
from typing import Dict, Tuple, List, Optional

from src.test_cast_dto import TestCase


@dataclass
class ParsedExecutionLog:
    """Unity/디바이스 실행 로그: TestResult(pass/fail)와 TestLog[GIVEN|EXPECTED] 블록.

    TestLog[ACTUAL]은 파싱하지 않는다.
    """

    results: Dict[str, str] = field(default_factory=dict)
    given_from_log: Dict[str, str] = field(default_factory=dict)
    expected_from_log: Dict[str, str] = field(default_factory=dict)

    def has_any_data(self) -> bool:
        return bool(self.results or self.given_from_log or self.expected_from_log)


class LogResultProcessor:
    LOG_RESULT_PATTERN = re.compile(
        r"TestResult\s*:\s*(?P<name>.+?)\s*\[(?P<status>pass|fail)\]",
        re.IGNORECASE,
    )
    # 배열: TestLog[GIVEN] : plaintext(16) [0x6B, 0xC1, ...]  (test_common.c print_array)
    # ACTUAL은 의도적으로 제외한다.
    TEST_LOG_ARRAY_PATTERN = re.compile(
        r"^TestLog\[(?P<kind>GIVEN|EXPECTED)\]\s*:\s*(?P<label>[^(\s]+?)\s*\((?P<blen>\d+)\)\s*\[(?P<inner>[^\]]*)\]\s*$",
        re.IGNORECASE,
    )
    # 스칼라: TestLog[GIVEN] : keyIdx [0x000000c9]  (print_string_and_value, %08lx)
    TEST_LOG_SCALAR_PATTERN = re.compile(
        r"^TestLog\[(?P<kind>GIVEN|EXPECTED)\]\s*:\s*(?P<label>.+?)\s*\[(?P<val>0x[0-9A-Fa-f]+)\]\s*$",
        re.IGNORECASE,
    )

    @classmethod
    def parse(cls, log_content: str) -> ParsedExecutionLog:
        out = ParsedExecutionLog()
        if not log_content:
            return out

        given_buf: List[str] = []
        exp_buf: List[str] = []

        def append_test_log_entry(kind: str, entry: str) -> None:
            kind_upper = kind.upper()
            if kind_upper == "GIVEN":
                given_buf.append(entry)
            elif kind_upper == "EXPECTED":
                exp_buf.append(entry)

        def flush_buffers(test_key: str) -> None:
            if given_buf:
                out.given_from_log[test_key] = ", ".join(given_buf)
            if exp_buf:
                out.expected_from_log[test_key] = ", ".join(exp_buf)
            given_buf.clear()
            exp_buf.clear()

        for raw in log_content.splitlines():
            stripped = raw.strip("\r").strip()
            if not stripped:
                continue

            tr = cls.LOG_RESULT_PATTERN.search(stripped)
            if tr:
                name = tr.group("name").strip()
                status = tr.group("status").strip().lower()
                if name:
                    flush_buffers(name)
                    if status == "pass":
                        out.results[name] = "PASS"
                    elif status == "fail":
                        out.results[name] = "FAIL"
                continue

            arr = cls.TEST_LOG_ARRAY_PATTERN.match(stripped)
            if arr:
                kind = arr.group("kind")
                label = arr.group("label").strip()
                blen = arr.group("blen")
                inner = arr.group("inner") or ""
                tokens = re.findall(r"0x[0-9A-Fa-f]+", inner, flags=re.IGNORECASE)
                hex_space = " ".join(tokens)
                entry = f"{label}({blen})={hex_space}" if hex_space else f"{label}({blen})="
                append_test_log_entry(kind, entry)
                continue

            sca = cls.TEST_LOG_SCALAR_PATTERN.match(stripped)
            if sca:
                kind = sca.group("kind")
                label = sca.group("label").strip()
                val = sca.group("val")
                append_test_log_entry(kind, f"{label}={val}")
                continue

        return out

    @staticmethod
    def _build_lookups(
        test_cases: List[TestCase],
    ) -> Tuple[Dict[str, TestCase], Dict[str, List[TestCase]]]:
        by_full: Dict[str, TestCase] = {}
        for c in test_cases:
            g, t = c.group_name, c.test_name
            by_full[f"{g}::{t}"] = c
            by_full[f"{g}.{t}"] = c
        by_short: Dict[str, List[TestCase]] = {}
        for c in test_cases:
            by_short.setdefault(c.test_name, []).append(c)
        return by_full, by_short

    @staticmethod
    def _resolve_case(
        name: str,
        by_full: Dict[str, TestCase],
        by_short: Dict[str, List[TestCase]],
    ) -> Optional[TestCase]:
        if not name:
            return None
        if name in by_full:
            return by_full[name]
        dotted = name.replace("::", ".")
        if dotted in by_full:
            return by_full[dotted]
        doubled = name.replace(".", "::")
        if doubled in by_full:
            return by_full[doubled]
        candidates = by_short.get(name)
        if candidates and len(candidates) == 1:
            return candidates[0]
        return None

    @classmethod
    def apply_to_cases(
        cls,
        test_cases: List[TestCase],
        parsed: ParsedExecutionLog,
    ) -> Tuple[int, Dict[str, str], int, Dict[str, str], int, Dict[str, str]]:
        """로그를 테스트 케이스에 반영한다.

        Returns:
            (results_applied, results_unmatched,
             given_applied, given_unmatched,
             expected_applied, expected_unmatched)
        """
        by_full, by_short = cls._build_lookups(test_cases)

        results_applied = 0
        results_unmatched: Dict[str, str] = {}
        for test_name, status in parsed.results.items():
            case = cls._resolve_case(test_name, by_full, by_short)
            if case:
                case.result = status
                results_applied += 1
            else:
                results_unmatched[test_name] = status

        given_applied = 0
        given_unmatched: Dict[str, str] = {}
        for key, blob in parsed.given_from_log.items():
            case = cls._resolve_case(key, by_full, by_short)
            if case:
                case.given_data = blob
                given_applied += 1
            else:
                given_unmatched[key] = blob[:120] + ("..." if len(blob) > 120 else "")

        # Expected Data (TestLog[EXPECTED] only; ACTUAL is ignored)
        expected_applied = 0
        expected_unmatched: Dict[str, str] = {}
        for key, blob in parsed.expected_from_log.items():
            case = cls._resolve_case(key, by_full, by_short)
            if case:
                case.expected_data = blob
                expected_applied += 1
            else:
                expected_unmatched[key] = blob[:120] + ("..." if len(blob) > 120 else "")

        return (
            results_applied,
            results_unmatched,
            given_applied,
            given_unmatched,
            expected_applied,
            expected_unmatched,
        )
