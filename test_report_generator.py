import os
import hashlib
import argparse
from typing import Dict, Tuple, Optional

from src.meta_info import load_meta_info
from src.vector_extractor import VectorExtractor
from src.unity_test_parser import UnityTestParser
from src.test_cast_dto import TestCase
from src.data_parser import DataParser
from src.log_retsult_processor import LogResultProcessor
from src.report_generator import ReportGenerator


def load_log_results(log_arg: str) -> Tuple[Dict[str, str], Optional[str], Optional[str]]:
    if not log_arg:
        return {}, None, None
    
    if os.path.isfile(log_arg):
        try:
            with open(log_arg, 'rb') as f:
                raw_bytes = f.read()
            log_text = raw_bytes.decode('utf-8', errors='ignore')
            sha256 = hashlib.sha256(raw_bytes).hexdigest()[56:]
            source_name = os.path.basename(log_arg)
            return LogResultProcessor.parse(log_text), source_name, sha256
        except OSError as e:
            print(f"[!] Log file not found: {e}")
            return {}, None, None
    
    return {}, None, None


def main():
    parser = argparse.ArgumentParser(description='Generate advanced report for Unity tests')
    parser.add_argument('--parse', action='store_true', help='Parse only')
    parser.add_argument('--test-dir', default='test', help='Test directory')
    parser.add_argument('--root', default='.', help='Project root')
    parser.add_argument('--title', default='', help='Report title (empty for "Untitled")')
    parser.add_argument('--meta-json', default='', help='Meta information to display at the top (JSON string or file path)')
    parser.add_argument('--log-file', default='', help='Test execution log (file path or original string)')
    parser.add_argument('--show-git-info', action='store_true', help='Show Git information')
    
    args = parser.parse_args()
    
    print("\n[*] Parsing test code...")
    parser_obj = UnityTestParser(test_dir=args.test_dir, project_root=args.root)
    test_cases = parser_obj.parse_all_tests()
    
    print(f"[+] Found {len(test_cases)} test cases\n")
    
    if args.parse:
        return
    
    meta_info = load_meta_info(args.meta_json)
    log_results, log_source_name, log_sha256 = load_log_results(args.log_file)
    if log_results:
        applied, unmatched = LogResultProcessor.apply_to_cases(test_cases, log_results)
        print(f"[+] Applied {applied} log-based results")
        if unmatched:
            sample = ', '.join(list(unmatched.keys())[:5])
            print(f"[!] Not found test results in code: {len(unmatched)} cases: {sample}")
    
    print("[*] Generating report...\n")
    generator = ReportGenerator(
        test_cases,
        parser_obj.vector_extractor,
        title=args.title,
        meta_info=meta_info,
        project_root=args.root,
        log_source_name=log_source_name,
        log_sha256=log_sha256,
        show_git_info=args.show_git_info,
    )
    
    output_file = generator.generate_html_report()
    print(f"[+] HTML report generated: {output_file}\n")
    print("[OK] Completed!\n")

if __name__ == '__main__':
    main()

