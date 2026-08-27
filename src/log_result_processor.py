import re
from dataclasses import dataclass, field
from typing import Dict, Tuple, List, Optional

from src.test_cast_dto import TestCase


@dataclass
class LogEntry:
    """실행 로그 한 줄. GIVEN/EXPECTED/ACTUAL 순서나 개수 대칭을 가정하지 않는다."""

    kind: str
    key: str
    value: str

    def as_assignment(self) -> str:
        return f"{self.key}={self.value}"


@dataclass
class ParsedExecutionLog:
    """Unity/디바이스 실행 로그: TestResult(pass/fail)와 TestLog[GIVEN|EXPECTED|ACTUAL] 블록."""

    results: Dict[str, str] = field(default_factory=dict)
    given_from_log: Dict[str, str] = field(default_factory=dict)
    expected_from_log: Dict[str, str] = field(default_factory=dict)
    actual_from_log: Dict[str, str] = field(default_factory=dict)
    entries_by_test: Dict[str, List[LogEntry]] = field(default_factory=dict)

    def has_any_data(self) -> bool:
        return bool(
            self.results
            or self.given_from_log
            or self.expected_from_log
            or self.actual_from_log
            or self.entries_by_test
        )


class LogResultProcessor:
    LOG_RESULT_PATTERN = re.compile(
        r"TestResult\s*:\s*(?P<name>.+?)\s*\[(?P<status>pass|fail)\]",
        re.IGNORECASE,
    )
    # 줄 앞 타임스탬프/파일 경로 접두어를 허용한다.
    TEST_LOG_PREFIX = re.compile(
        r"TestLog\[(?P<kind>GIVEN|EXPECTED|ACTUAL)\]\s*:\s*(?P<body>.*)$",
        re.IGNORECASE,
    )
    # 배열: ciphertext(64) [0x3A, 0xD7, ...]  (닫는 ] 포함, 한 줄)
    ARRAY_COMPLETE = re.compile(
        r"^(?P<label>[^(\s]+?)\s*\((?P<blen>\d+)\)\s*\[(?P<inner>.*)\]\s*$",
    )
    # 배열 시작만 있고 닫는 ] 없음 (UART/콘솔 줄바꿈)
    ARRAY_OPEN = re.compile(
        r"^(?P<label>[^(\s]+?)\s*\((?P<blen>\d+)\)\s*\[(?P<inner>.*)$",
    )
    SCALAR_BODY = re.compile(
        r"^(?P<label>.+?)\s*\[(?P<val>[^\]]+)\]\s*$",
    )

    @staticmethod
    def _hex_value_from_inner(inner: str) -> str:
        tokens = re.findall(r"0x[0-9A-Fa-f]+", inner or "", flags=re.IGNORECASE)
        return " ".join(tokens)

    @classmethod
    def _entry_from_array(cls, kind: str, label: str, blen: str, inner: str) -> LogEntry:
        hex_space = cls._hex_value_from_inner(inner)
        key = f"{label.strip()}({blen})"
        return LogEntry(kind=kind.upper(), key=key, value=hex_space)

    @classmethod
    def _parse_complete_body(cls, kind: str, body: str) -> Optional[LogEntry]:
        body = (body or "").strip()
        if not body:
            return None
        arr = cls.ARRAY_COMPLETE.match(body)
        if arr:
            return cls._entry_from_array(
                kind, arr.group("label"), arr.group("blen"), arr.group("inner") or ""
            )
        sca = cls.SCALAR_BODY.match(body)
        if sca:
            return LogEntry(
                kind=kind.upper(),
                key=sca.group("label").strip(),
                value=sca.group("val").strip(),
            )
        return None

    @classmethod
    def parse(cls, log_content: str) -> ParsedExecutionLog:
        out = ParsedExecutionLog()
        if not log_content:
            return out

        entries: List[LogEntry] = []
        pending: Optional[Dict[str, str]] = None

        def commit_pending() -> None:
            nonlocal pending
            if not pending:
                return
            entries.append(
                cls._entry_from_array(
                    pending["kind"],
                    pending["label"],
                    pending["blen"],
                    pending.get("inner", ""),
                )
            )
            pending = None

        def flush_buffers(test_key: str) -> None:
            commit_pending()
            if not entries:
                return
            given = [e.as_assignment() for e in entries if e.kind == "GIVEN"]
            exp = [e.as_assignment() for e in entries if e.kind == "EXPECTED"]
            act = [e.as_assignment() for e in entries if e.kind == "ACTUAL"]
            out.entries_by_test[test_key] = list(entries)
            if given:
                out.given_from_log[test_key] = ", ".join(given)
            if exp:
                out.expected_from_log[test_key] = ", ".join(exp)
            if act:
                out.actual_from_log[test_key] = ", ".join(act)
            entries.clear()

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

            log_m = cls.TEST_LOG_PREFIX.search(stripped)
            if log_m:
                commit_pending()
                kind = log_m.group("kind")
                body = log_m.group("body") or ""
                complete = cls._parse_complete_body(kind, body)
                if complete:
                    entries.append(complete)
                    continue
                opened = cls.ARRAY_OPEN.match(body.strip())
                if opened:
                    pending = {
                        "kind": kind.upper(),
                        "label": opened.group("label").strip(),
                        "blen": opened.group("blen"),
                        "inner": opened.group("inner") or "",
                    }
                continue

            if pending:
                pending["inner"] = f"{pending.get('inner', '')} {stripped}"
                if "]" in stripped:
                    commit_pending()

        return out

    @staticmethod
    def group_rounds(
        entries: List[LogEntry],
    ) -> Tuple[List[LogEntry], List[Tuple[List[LogEntry], List[LogEntry]]]]:
        """GIVEN은 입력으로 모으고, EXPECTED/ACTUAL은 호출 단위 라운드로 묶는다.

        ACTUAL 뒤에 다시 EXPECTED가 오면 새 라운드. 개수/순서가 대칭일 필요는 없다.
        """
        given = [e for e in entries if e.kind == "GIVEN"]
        rounds: List[Tuple[List[LogEntry], List[LogEntry]]] = []
        exp: List[LogEntry] = []
        act: List[LogEntry] = []
        last_kind: Optional[str] = None
        for e in entries:
            if e.kind == "GIVEN":
                continue
            if e.kind == "EXPECTED" and last_kind == "ACTUAL" and (exp or act):
                rounds.append((exp, act))
                exp, act = [], []
            if e.kind == "EXPECTED":
                exp.append(e)
            elif e.kind == "ACTUAL":
                act.append(e)
            last_kind = e.kind
        if exp or act:
            rounds.append((exp, act))
        return given, rounds

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
    ) -> Tuple[
        int, Dict[str, str],
        int, Dict[str, str],
        int, Dict[str, str],
        int, Dict[str, str],
    ]:
        """로그를 테스트 케이스에 반영한다.

        Returns:
            (results_applied, results_unmatched,
             given_applied, given_unmatched,
             expected_applied, expected_unmatched,
             actual_applied, actual_unmatched)
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

        for key, entries in parsed.entries_by_test.items():
            case = cls._resolve_case(key, by_full, by_short)
            if case:
                case.log_entries = entries

        given_applied = 0
        given_unmatched: Dict[str, str] = {}
        for key, blob in parsed.given_from_log.items():
            case = cls._resolve_case(key, by_full, by_short)
            if case:
                case.given_data = blob
                given_applied += 1
            else:
                given_unmatched[key] = blob[:120] + ("..." if len(blob) > 120 else "")

        expected_applied = 0
        expected_unmatched: Dict[str, str] = {}
        for key, blob in parsed.expected_from_log.items():
            case = cls._resolve_case(key, by_full, by_short)
            if case:
                case.expected_data = blob
                expected_applied += 1
            else:
                expected_unmatched[key] = blob[:120] + ("..." if len(blob) > 120 else "")

        actual_applied = 0
        actual_unmatched: Dict[str, str] = {}
        for key, blob in parsed.actual_from_log.items():
            case = cls._resolve_case(key, by_full, by_short)
            if case:
                case.actual_data = blob
                actual_applied += 1
            else:
                actual_unmatched[key] = blob[:120] + ("..." if len(blob) > 120 else "")

        return (
            results_applied,
            results_unmatched,
            given_applied,
            given_unmatched,
            expected_applied,
            expected_unmatched,
            actual_applied,
            actual_unmatched,
        )
