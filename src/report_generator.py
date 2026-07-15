import os
import re
import sys
import html
import shutil
from typing import List, Dict, Optional, Union
from datetime import datetime
from collections import defaultdict
from src.test_cast_dto import TestCase
from src.vector_extractor import VectorExtractor
from src.data_parser import DataParser
from src.get_git_info import get_git_info
from src.version import get_report_generator_version


class ReportGenerator:
    output_dir = "output_report"
    META_FIELDS = []
    
    def __init__(
        self,
        test_cases: List[TestCase],
        vector_extractor: VectorExtractor,
        title: str = "",
        meta_info: Optional[Union[Dict[str, str], List[Dict[str, str]]]] = None,
        project_root: str = ".",
        log_source_name: Optional[str] = None,
        log_sha256: Optional[str] = None,
        log_source_path: Optional[str] = None,
        show_git_info: bool = True,
    ):
        self.test_cases = test_cases
        self.vector_extractor = vector_extractor
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # If title is empty, use "Untitled"
        self.title = title.strip() if title and title.strip() else "Untitled"
        if meta_info is None:
            self.meta_info = {}
        else:
            self.meta_info = meta_info
        self.project_root = os.path.abspath(project_root) if project_root else os.getcwd()
        self.meta_label_map = {}
        for label, keys in self.META_FIELDS:
            for key in keys:
                self.meta_label_map[key.lower()] = label
        self.log_source_name = log_source_name
        self.log_sha256 = log_sha256
        self.log_source_path = log_source_path
        self.report_version = get_report_generator_version()
        self.data_toggle_counter = 0
        self.show_git_info = show_git_info
        self.generated_group_reports: List[str] = []
        self.report_bundle_dir: Optional[str] = None
    
    def _format_data_with_tooltips(self, data_str: str) -> str:
        """Format data string into HTML (variable-by-variable newline + actual array value tooltip)
        
        Supported formats:
        1. General value: key_id=5
        2. Variable: key_data=test_key_storage_aes
        3. File specification: key_data=[src:test/common/test_vector.c]test_key_storage_aes
        """
        if data_str == '-':
            return '<span style="color: #999;">-</span>'
        
        items = DataParser.parse_variables(data_str)
        if not items:
            return data_str
        
        html_parts = []
        for item in items:
            key = item[0]
            val = item[1]
            file_path = item[2] if len(item) > 2 else None
            key_str = str(key) if key is not None else ""
            val_str = str(val) if val is not None else ""
            key_html = html.escape(key_str)
            val_escaped = html.escape(val_str, quote=True)
            file_info = ""
            if file_path:
                file_info = f" <small style='color: #999;'>[from {html.escape(file_path)}]</small>"
            
            # Get variable value representations
            tooltip_from_file = self.vector_extractor.get_formatted_value(val, file_path=file_path)
            literal_value = self.vector_extractor.get_literal_value(val, file_path=file_path)
            scalar_info = self.vector_extractor.get_scalar_value(val, file_path=file_path)
            is_string_var = self.vector_extractor.is_string_variable(val, file_path=file_path)

            inline_formatted = None
            if not tooltip_from_file and not file_path:
                inline_formatted = self.vector_extractor.get_formatted_inline_byte_string(val)
            tooltip_text = tooltip_from_file or inline_formatted

            # 로그 인라인 바이트만 자세히에 넣는 경우: 헤더에 긴 hex 나열은 숨김
            hide_header_hex_preview = (
                inline_formatted is not None
                and not literal_value
                and not scalar_info
                and not is_string_var
            )
            header_value_code = (
                ""
                if hide_header_hex_preview
                else f'<code style="background-color: #e7f3ff; color: #0066cc;">{val_escaped}</code>'
            )

            if tooltip_text or literal_value or scalar_info:
                detail_sections = []
                if literal_value:
                    literal_html = html.escape(literal_value).replace('\n', '<br/>')
                    detail_sections.append(f'''
                        <div class="detail-block">
                            <div class="detail-block-label">문자열 값</div>
                            <div class="literal-block">{literal_html}</div>
                        </div>
                    ''')
                if tooltip_text and not is_string_var:
                    if '<br/>' in tooltip_text:
                        array_body = tooltip_text.replace('<br/>', '\n')
                        array_markup = f'<pre class="array-block">{array_body}</pre>'
                    else:
                        array_markup = f'<code class="array-inline">[{tooltip_text}]</code>'
                    detail_sections.append(f'''
                        <div class="detail-block">
                            <div class="detail-block-label">바이트 배열</div>
                            {array_markup}
                        </div>
                    ''')
                if scalar_info:
                    raw_value = html.escape(str(scalar_info.get('raw', '')).strip())
                    type_name = html.escape(str(scalar_info.get('type', '')))
                    numeric_line = ''
                    int_value = scalar_info.get('int')
                    if isinstance(int_value, int):
                        hex_value = f"0x{int_value:X}" if int_value >= 0 else f"-0x{abs(int_value):X}"
                        numeric_line = f'<div class="scalar-detail-line">dec {int_value} &nbsp;|&nbsp; hex {hex_value}</div>'
                    detail_sections.append(f'''
                        <div class="detail-block">
                            <div class="detail-block-label">정수 값 ({type_name})</div>
                            <div class="scalar-block">
                                <code>{raw_value}</code>
                                {numeric_line}
                            </div>
                        </div>
                    ''')
                detail_display = ''.join(detail_sections)
                toggle_id = f"data-detail-{self.data_toggle_counter}"
                self.data_toggle_counter += 1
                
                html_part = f'''
                <div class="data-entry">
                    <div class="data-entry-header">
                        <div class="data-entry-info">
                            <strong>{key_html}:</strong>
                            {header_value_code}{file_info}
                        </div>
                        <button type="button" class="data-toggle-btn" data-target="{toggle_id}" aria-expanded="false">Details</button>
                    </div>
                    <div id="{toggle_id}" class="data-entry-detail">
                        {detail_display}
                    </div>
                </div>'''
            else:
                if file_path:
                    html_part = f'''
                <div class="data-entry data-entry-warning">
                    <div class="data-entry-header">
                        <div class="data-entry-info">
                            <strong>{key_html}:</strong>
                            <code style="background-color: #fff3cd; color: #856404;">{val_escaped}</code>{file_info}
                            <span style="font-size: 10px; color: #999;">(value not found)</span>
                        </div>
                    </div>
                </div>'''
                else:
                    html_part = f'''
                <div class="data-entry">
                    <div class="data-entry-header">
                        <div class="data-entry-info">
                            <strong>{key_html}:</strong>
                            <code style="background-color: #f5f5f5; color: #333;">{val_escaped}</code>
                        </div>
                    </div>
                </div>'''
            
            html_parts.append(html_part)
        
        return ''.join(html_parts)

    def _is_empty_data(self, data_str: Optional[str]) -> bool:
        return not data_str or data_str.strip() in ('', '-')

    @staticmethod
    def _sanitize_group_slug(group_name: str) -> str:
        slug = re.sub(r"[^\w\-]+", "_", group_name or "unknown", flags=re.UNICODE)
        slug = slug.strip("_")
        return slug or "unknown"

    def _group_report_filename(self, group_name: str) -> str:
        return f"test_report_{self._sanitize_group_slug(group_name)}.html"

    def _get_meta_label(self, key: str) -> str:
        if not key:
            return ""
        lookup_key = key.lower()
        return self.meta_label_map.get(lookup_key, key)
    
    def _render_meta_section(self) -> str:
        if not self.meta_info:
            return ""
        
        extracted_items = []
        
        def append_items_from_dict(source: Dict[str, Union[str, int, float]]):
            if not isinstance(source, dict):
                return
            
            for key, raw_value in source.items():
                value_str = str(raw_value).strip()
                if not value_str:
                    continue
                label = self._get_meta_label(str(key))
                extracted_items.append((label, value_str))
        
        if isinstance(self.meta_info, list):
            if not self.meta_info:
                return ""
            for entry in self.meta_info:
                append_items_from_dict(entry if isinstance(entry, dict) else {})
        elif isinstance(self.meta_info, dict):
            append_items_from_dict(self.meta_info)
        else:
            return ""
        
        if not extracted_items:
            return ""
        
        cards_html = ''.join(
            f'''
            <div class="meta-card">
                <div class="meta-label">{label}</div>
                <div class="meta-value">{value}</div>
            </div>
            '''
            for label, value in extracted_items
        )
        
        return f'''
        <div class="meta-section">
            <div class="meta-grid">
                {cards_html}
            </div>
        </div>
        '''
    
    
    def _get_stats(self) -> Dict:
        """Calculate statistics"""
        return {
            'total': len(self.test_cases),
            'passed': sum(1 for case in self.test_cases if case.result == "PASS"),
            'failed': sum(1 for case in self.test_cases if case.result == "FAIL"),
            'not_run': sum(1 for case in self.test_cases if case.result == "Not Run"),
        }
    
    def generate_html_report(
        self,
        output_file: Optional[str] = None,
        split_by_group: bool = True,
        nav_html: str = "",
        hide_group_stats: bool = False,
        write_dir: Optional[str] = None,
    ) -> str:
        """Generate HTML report bundle under output_report/test_report_<timestamp>/."""
        if split_by_group:
            self.generated_group_reports = []
            report_folder_name = f"test_report_{self.timestamp}"
            bundle_dir = os.path.join(self.output_dir, report_folder_name)
            os.makedirs(bundle_dir, exist_ok=True)
            self.report_bundle_dir = bundle_dir
            write_dir = bundle_dir
            if output_file is None:
                output_file = "test_report.html"

            # Copy referenced log into the report folder for offline linking
            if self.log_source_path and os.path.isfile(self.log_source_path):
                log_name = self.log_source_name or os.path.basename(self.log_source_path)
                try:
                    shutil.copy2(
                        self.log_source_path,
                        os.path.join(bundle_dir, log_name),
                    )
                    self.log_source_name = log_name
                except OSError as e:
                    print(f"[!] Failed to copy log file into report folder: {e}", file=sys.stderr)
        else:
            if output_file is None:
                output_file = f"test_report_{self.timestamp}.html"
            if write_dir is None:
                write_dir = self.report_bundle_dir or self.output_dir
        
        stats = self._get_stats()
        
        # Group by group
        group_stats = {}
        for case in self.test_cases:
            if case.group_name not in group_stats:
                group_stats[case.group_name] = {'total': 0, 'passed': 0, 'failed': 0}
            group_stats[case.group_name]['total'] += 1
            if case.result == "PASS":
                group_stats[case.group_name]['passed'] += 1
            elif case.result == "FAIL":
                group_stats[case.group_name]['failed'] += 1
        
        pass_rate = (stats['passed'] / stats['total'] * 100) if stats['total'] > 0 else 0
        pass_rate_clamped = max(0.0, min(100.0, pass_rate))
        
        # Create table rows
        table_rows = ""
        for idx, case in enumerate(self.test_cases, 1):
            test_id_attr = html.escape(case.test_id or "")
            group_attr = html.escape(case.group_name or "")
            # Combine test name and group name (one column)
            group_label = html.escape(case.group_name) if case.group_name else '-'
            test_name_raw = case.test_name if case.test_name else '-'
            test_name_html = html.escape(test_name_raw)
            test_name_tooltip = html.escape(test_name_raw, quote=True)
            file_name = os.path.basename(case.file_path) if case.file_path else ''
            file_info = f'[from {file_name}]' if file_name else ''
            group_test_display = (
                f'<span class="badge badge-group">{group_label}</span><br/>'
                f'<code title="{test_name_tooltip}">{test_name_html}</code><br/>'
                f'<small style="color: #999;">{html.escape(file_info)}</small>'
            )
            
            # PreCondition text representation (single box with numbered items)
            precond_empty = self._is_empty_data(case.precondition)
            if not precond_empty:
                precond_items = [
                    line.strip()
                    for line in case.precondition.split(',')
                    if line.strip()
                ]
                precond_rows = []
                for num, item in enumerate(precond_items, 1):
                    precond_rows.append(
                        f'<div class="precond-item">'
                        f'<span class="precond-num">{num}</span>'
                        f'<span class="precond-text">{html.escape(item)}</span>'
                        f'</div>'
                    )
                precond_display = (
                    f'<div class="precond-box">{"".join(precond_rows)}</div>'
                )
            else:
                precond_display = '<span style="color: #999;">-</span>'
            
            # Description text (newline by comma; leading "·" when content exists)
            if case.description and case.description.strip():
                desc_items = [
                    line.strip()
                    for line in case.description.split(',')
                    if line.strip()
                ]
                desc_lines = [
                    f'<span class="desc-bullet">·</span> {html.escape(item)}'
                    for item in desc_items
                ]
                desc_display = f'<div class="desc-text">{"<br/>".join(desc_lines)}</div>'
            else:
                desc_display = '<span style="color: #999;">-</span>'
            
            # Data panel: PreCondition / Given / Expected (expand below row on click)
            given_empty = self._is_empty_data(case.given_data)
            expected_empty = self._is_empty_data(case.expected_data)
            given_display = (
                '<span style="color: #999;">-</span>'
                if given_empty
                else self._format_data_with_tooltips(case.given_data)
            )
            expected_display = (
                '<span style="color: #999;">-</span>'
                if expected_empty
                else self._format_data_with_tooltips(case.expected_data)
            )
            detail_id = f"row-data-{idx}"
            has_data_detail = not precond_empty or not given_empty or not expected_empty
            if has_data_detail:
                data_cell = (
                    f'<button type="button" class="row-data-toggle-btn" '
                    f'data-target="{detail_id}" aria-expanded="false">View</button>'
                )
            else:
                data_cell = '<span style="color: #999;">-</span>'
            
            # Result badge
            if case.result == "PASS":
                status_badge = '<span style="color: #28a745; font-weight: 700;">✓ PASS</span>'
            elif case.result == "FAIL":
                status_badge = '<span style="color: #dc3545; font-weight: 700;">✗ FAIL</span>'
            else:
                status_badge = '<span style="color: #ffc107; font-weight: 700;">⊘ Not Run</span>'
            
            if case.test_id:
                test_id_html = html.escape(case.test_id)
                test_id_tooltip = html.escape(case.test_id, quote=True)
                test_id_display = (
                    f'<span class="test-id-text" title="{test_id_tooltip}">{test_id_html}</span>'
                )
            else:
                test_id_display = '-'
            
            detail_row = ""
            if has_data_detail:
                detail_row = f'''
                <tr id="{detail_id}" class="data-detail-row" hidden>
                    <td colspan="6">
                        <div class="data-detail-panel">
                            <div class="data-detail-column data-detail-full">
                                <div class="data-detail-title">PreCondition</div>
                                {precond_display}
                            </div>
                            <div class="data-detail-column">
                                <div class="data-detail-title">Given Data</div>
                                {given_display}
                            </div>
                            <div class="data-detail-column">
                                <div class="data-detail-title">Actual Data</div>
                                {expected_display}
                            </div>
                        </div>
                    </td>
                </tr>
'''
            
            table_rows += f'''
                <tr class="test-row" data-index="{idx}" data-test-id="{test_id_attr}" data-group="{group_attr}" data-detail-id="{detail_id if has_data_detail else ''}">
                    <td>{idx}</td>
                    <td>{test_id_display}</td>
                    <td>{group_test_display}</td>
                    <td>{desc_display}</td>
                    <td class="data-toggle-cell">{data_cell}</td>
                    <td>{status_badge}</td>
                </tr>
{detail_row}'''
        
        # Group by group (clickable links to per-group HTML)
        cases_by_group: Dict[str, List[TestCase]] = defaultdict(list)
        for case in self.test_cases:
            cases_by_group[case.group_name or "unknown"].append(case)

        group_file_map = {
            group_name: self._group_report_filename(group_name)
            for group_name in sorted(group_stats.keys())
        }

        group_rows = ""
        for group_name, group_data in sorted(group_stats.items()):
            group_pass_rate = (group_data['passed'] / group_data['total'] * 100) if group_data['total'] > 0 else 0
            group_href = html.escape(group_file_map[group_name], quote=True)
            group_label = html.escape(group_name)
            group_rows += f'''
                <tr>
                    <td><a class="group-link" href="{group_href}">{group_label}</a></td>
                    <td>{group_data['total']}</td>
                    <td><span class="badge badge-success">{group_data['passed']}</span></td>
                    <td><span class="badge badge-danger">{group_data['failed']}</span></td>
                    <td><strong>{group_pass_rate:.1f}%</strong></td>
                </tr>
'''
        info_lines = []
        meta_section_html = self._render_meta_section()
        
        if self.show_git_info is True:
            git_commit, git_branch, git_tag = get_git_info(self.project_root)
            
            if git_commit or git_branch or git_tag:
                commit_display = git_commit[:7] if git_commit else "N/A"
                branch_display = git_branch if git_branch else "N/A"
                tag_display = git_tag if git_tag else None
                
                git_line = "GIT ["
                if tag_display:
                    git_line += f"tag: {tag_display} | "
                git_line += f"branch: {branch_display} | commit: {commit_display}"
                git_line += "]"
                info_lines.append(git_line)
            
        if self.log_source_name:
            log_name = html.escape(self.log_source_name)
            log_href = html.escape(self.log_source_name, quote=True)
            checksum = html.escape(str(self.log_sha256 or "N/A"))
            info_lines.append(
                f'Log [file: <a class="log-link" href="{log_href}">{log_name}</a>'
                f' | checksum(SHA256): {checksum}]'
            )
        
        info_text = "<br/>".join(info_lines)
        version_display = html.escape(self.report_version)
        footer_html = f'''
        <div class="footer">
            <strong>Test Report Generator</strong> v{version_display}
        </div>
        '''
        
        html_content = f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{ 
            max-width: 1600px; 
            margin: 0 auto; 
            background: white; 
            border-radius: 12px; 
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }}
        .header {{ 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; 
            padding: 40px; 
            text-align: center;
        }}
        .header h1 {{ font-size: 32px; margin-bottom: 10px; font-weight: 700; }}
        .header a.log-link {{
            color: #ffffff;
            text-decoration: underline;
            font-weight: 600;
        }}
        .header a.log-link:hover {{
            color: #f0f4ff;
        }}
        .meta-section {{
            padding: 20px 30px;
            background: #ffffff;
            border-bottom: 1px solid #e9ecef;
        }}
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 16px;
        }}
        .meta-card {{
            background: #f8f9ff;
            border: 1px solid #e3e6ff;
            border-radius: 10px;
            padding: 16px 20px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.03);
        }}
        .meta-label {{
            font-size: 11px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.6px;
            margin-bottom: 6px;
        }}
        .meta-value {{
            font-size: 16px;
            font-weight: 600;
            color: #1f1f1f;
        }}
        .stats-container {{ 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); 
            gap: 28px; 
            padding: 40px 30px;
            background: #f8f9fa;
            border-bottom: 1px solid #e9ecef;
        }}
        .stat-box {{ 
            padding: 14px; 
            border-radius: 8px; 
            text-align: center;
            background: white;
            border-left: 4px solid #667eea;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            min-height: 110px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            gap: 8px;
        }}
        .stat-box h3 {{ font-size: 32px; font-weight: bold; margin: 0; }}
        .pass-rate {{ 
            grid-column: 1 / -1;
            padding: 28px;
            background: white;
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            gap: 14px;
            border-left: 4px solid #667eea;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }}
        .pass-rate-header {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            width: 100%;
        }}
        .pass-rate .label {{
            font-size: 15px;
            font-weight: 600;
            color: #333;
        }}
        .pass-rate .value {{
            font-size: 30px;
            font-weight: 700;
            color: #2c3e50;
        }}
        .progress-track {{
            width: 100%;
            height: 22px;
            background: #eef2ff;
            border-radius: 999px;
            overflow: hidden;
            position: relative;
        }}
        .progress-bar {{
            height: 100%;
            background: linear-gradient(135deg, #42e695 0%, #3bb2b8 100%);
            border-radius: inherit;
            box-shadow: inset 0 1px 3px rgba(0,0,0,0.1);
            transition: width 0.4s ease;
        }}
        .progress-percent {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 12px;
            font-weight: 600;
            color: #1b2a41;
        }}
        .section {{ padding: 30px; }}
        .section-title {{ 
            font-size: 20px; 
            font-weight: 700; 
            margin-bottom: 20px;
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }}
        table {{ 
            width: 100%; 
            border-collapse: collapse;
            background: white;
            font-size: 12px;
            table-layout: fixed;
        }}
        th {{ 
            background: #f8f9fa;
            padding: 12px;
            text-align: left; 
            border-bottom: 2px solid #dee2e6;
            font-weight: 600;
            color: #333;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        th.sortable {{
            cursor: pointer;
            position: relative;
            padding-right: 28px;
        }}
        th.sortable::after {{
            content: '⇅';
            position: absolute;
            right: 10px;
            font-size: 11px;
            color: #bbb;
        }}
        th.sorted-asc::after {{
            content: '▲';
            color: #444;
        }}
        th.sorted-desc::after {{
            content: '▼';
            color: #444;
        }}
        td {{ 
            padding: 12px; 
            border-bottom: 1px solid #dee2e6;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        /* 상세 테스트 결과 테이블 칼럼 너비 */
        th:nth-child(1), td:nth-child(1) {{ width: 5%; text-align: center; }}  /* No. */
        th:nth-child(2), td:nth-child(2) {{ width: 15%; text-align: center; }}  /* Test ID */
        td:nth-child(2) {{
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .test-id-text {{
            display: block;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            cursor: default;
        }}
        th:nth-child(3), td:nth-child(3) {{ width: 25%; }}  /* Group / Test Name / File */
        th:nth-child(4), td:nth-child(4) {{ width: 30%; text-align: left; }}  /* Description */
        td:nth-child(4) {{ overflow: visible; }}  /* Allow multiline description */
        th:nth-child(5), td:nth-child(5) {{ width: 10%; text-align: center; }}  /* Data */
        th:nth-child(6), td:nth-child(6) {{ width: 10%; text-align: center; }}  /* Result */
        td.data-toggle-cell {{
            text-align: center;
            vertical-align: middle;
            overflow: visible;
        }}
        .row-data-toggle-btn {{
            border: none;
            background: #667eea;
            color: #fff;
            font-size: 11px;
            padding: 5px 14px;
            border-radius: 999px;
            cursor: pointer;
            transition: background 0.2s ease;
        }}
        .row-data-toggle-btn:hover {{
            background: #5568d3;
        }}
        .row-data-toggle-btn.active {{
            background: #4451b8;
        }}
        tr.data-detail-row > td {{
            background: #f4f6ff;
            padding: 0;
            border-bottom: 1px solid #d7dbff;
            overflow: visible;
        }}
        .data-detail-panel {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            padding: 16px 18px;
            text-align: left;
        }}
        .data-detail-column {{
            min-width: 0;
        }}
        .data-detail-full {{
            grid-column: 1 / -1;
        }}
        .data-detail-title {{
            font-size: 12px;
            font-weight: 700;
            color: #4451b8;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 0.4px;
        }}
        .precond-box {{
            display: flex;
            flex-direction: column;
            gap: 8px;
            padding: 12px 14px;
            background: #ffffff;
            border: 1px solid #cfd6ff;
            border-left: 4px solid #667eea;
            border-radius: 8px;
            box-shadow: 0 1px 2px rgba(102, 126, 234, 0.08);
        }}
        .precond-item {{
            display: flex;
            align-items: flex-start;
            gap: 10px;
        }}
        .precond-num {{
            flex-shrink: 0;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 22px;
            height: 22px;
            padding: 0 6px;
            border-radius: 999px;
            background: #667eea;
            color: #fff;
            font-size: 11px;
            font-weight: 700;
            line-height: 1;
        }}
        .precond-text {{
            font-size: 12px;
            line-height: 1.5;
            color: #333;
            word-break: break-word;
            padding-top: 1px;
        }}
        @media (max-width: 900px) {{
            .data-detail-panel {{
                grid-template-columns: 1fr;
            }}
        }}
        
        /* 그룹별 통계 테이블 */
        .group-stats-table {{
            table-layout: fixed;
        }}
        .group-stats-table th:nth-child(1) {{ width: 35%; text-align: center; }}  /* 그룹명 제목 */
        .group-stats-table td:nth-child(1) {{ width: 35%; text-align: left; }}  /* 그룹명 내용 */
        .group-stats-table th:nth-child(2), 
        .group-stats-table td:nth-child(2) {{ width: 15%; text-align: center; }}  /* 총 테스트 */
        .group-stats-table th:nth-child(3), 
        .group-stats-table td:nth-child(3) {{ width: 15%; text-align: center; }}  /* 성공 */
        .group-stats-table th:nth-child(4), 
        .group-stats-table td:nth-child(4) {{ width: 15%; text-align: center; }}  /* 실패 */
        .group-stats-table th:nth-child(5), 
        .group-stats-table td:nth-child(5) {{ width: 20%; text-align: center; }}  /* 통과율 */
        
        tr:hover {{ background: #f8f9fa; }}
        code {{ 
            background: #f5f5f5;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Monaco', monospace;
            font-size: 11px;
        }}
        
        .desc-text {{
            font-size: 12px;
            line-height: 1.5;
            color: #333;
            word-break: break-word;
        }}
        .desc-bullet {{
            color: #667eea;
            font-weight: 700;
            margin-right: 2px;
        }}
        
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            white-space: nowrap;
        }}
        
        .badge-group {{ background: #e7f3ff; color: #004085; }}
        .badge-success {{ background: #d4edda; color: #155724; }}
        .badge-danger {{ background: #f8d7da; color: #721c24; }}
        .group-link {{
            color: #4451b8;
            text-decoration: none;
            font-weight: 700;
        }}
        .group-link:hover {{
            text-decoration: underline;
        }}
        .group-hint {{
            padding: 0 0 12px;
            color: #555;
            font-size: 13px;
        }}
        .nav-back {{
            padding: 16px 30px 0;
            font-size: 13px;
            color: #4451b8;
        }}
        .nav-back a {{
            color: #4451b8;
            text-decoration: none;
            font-weight: 600;
        }}
        .nav-back a:hover {{
            text-decoration: underline;
        }}
        .data-entry {{
            margin-bottom: 8px;
            padding: 10px 12px;
            border: 1px solid #e0e7ff;
            border-radius: 8px;
            background: #f9faff;
        }}
        .data-entry-header {{
            display: flex;
            justify-content: space-between;
            gap: 12px;
            align-items: flex-start;
            flex-wrap: wrap;
        }}
        .data-entry-info {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            align-items: center;
            font-size: 12px;
        }}
        .data-toggle-btn {{
            border: none;
            background: #667eea;
            color: #fff;
            font-size: 11px;
            padding: 4px 12px;
            border-radius: 999px;
            cursor: pointer;
            transition: background 0.2s ease;
        }}
        .data-toggle-btn:hover {{
            background: #5568d3;
        }}
        .data-entry-detail {{
            display: none;
            margin-top: 8px;
            padding-top: 8px;
            border-top: 1px dashed #d7dbff;
            font-size: 11px;
            color: #1f1f1f;
        }}
        .data-entry-detail.active {{
            display: block;
        }}
        .data-entry-warning {{
            background: #fffaf0;
            border-color: #ffe3a3;
        }}
        .detail-block {{
            margin-bottom: 10px;
        }}
        .detail-block:last-child {{
            margin-bottom: 0;
        }}
        .detail-block-label {{
            font-size: 11px;
            font-weight: 600;
            color: #555;
            margin-bottom: 4px;
            letter-spacing: 0.4px;
            text-transform: uppercase;
        }}
        .literal-block {{
            font-size: 12px;
            line-height: 1.4;
            padding: 8px 10px;
            background: #ffffff;
            border: 1px solid #e0e7ff;
            border-radius: 6px;
            white-space: pre-wrap;
            word-break: break-word;
        }}
        .array-block {{
            margin: 0;
            padding: 10px;
            font-size: 11px;
            line-height: 1.5;
            background: #0f172a;
            color: #e2e8f0;
            border-radius: 6px;
            white-space: pre-wrap;
            word-break: break-word;
        }}
        .array-inline {{
            display: inline-block;
            padding: 6px 10px;
            background: #0f172a;
            color: #e2e8f0;
            border-radius: 6px;
            font-size: 11px;
        }}
        .scalar-block {{
            background: #ffffff;
            border: 1px solid #e0e7ff;
            border-radius: 6px;
            padding: 8px 10px;
            font-size: 12px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }}
        .scalar-detail-line {{
            font-size: 11px;
            color: #555;
        }}
        
        .footer {{
            text-align: center; 
            padding: 20px; 
            color: #999; 
            font-size: 12px; 
            border-top: 1px solid #eee;
            background: #f8f9fa;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🧪 {self.title}</h1>
            <p>생성 시간: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            <p>{info_text}</p>
        </div>
        
        {meta_section_html}
        
        <div class="stats-container">
            <div class="stat-box">
                <div style="font-size: 12px; color: #666; text-transform: uppercase; font-weight: 600;">총 테스트</div>
                <h3>{stats['total']}</h3>
            </div>
            <div class="stat-box">
                <div style="font-size: 12px; color: #666; text-transform: uppercase; font-weight: 600;">성공</div>
                <h3>{stats['passed']}</h3>
            </div>
            <div class="stat-box">
                <div style="font-size: 12px; color: #666; text-transform: uppercase; font-weight: 600;">실패</div>
                <h3>{stats['failed']}</h3>
            </div>
            <div class="stat-box">
                <div style="font-size: 12px; color: #666; text-transform: uppercase; font-weight: 600;">미실행</div>
                <h3>{stats['not_run']}</h3>
            </div>
            <div class="pass-rate">
                <div class="pass-rate-header">
                    <span class="label">전체 통과율</span>
                    <span class="value">{pass_rate:.1f}%</span>
                </div>
                <div class="progress-track">
                    <div class="progress-bar" style="width: {pass_rate_clamped:.1f}%;"></div>
                    <span class="progress-percent">{pass_rate:.1f}%</span>
                </div>
            </div>
        </div>
        
        <div class="section">
            <div class="section-title">📊 그룹별 통계</div>
            <p class="group-hint">그룹명을 클릭하면 해당 그룹의 상세 테스트 결과로 이동합니다.</p>
            <table class="group-stats-table">
                <thead>
                    <tr>
                        <th>그룹명</th>
                        <th>총 테스트</th>
                        <th>성공</th>
                        <th>실패</th>
                        <th>통과율</th>
                    </tr>
                </thead>
                <tbody>
                    {group_rows}
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <div class="section-title">📝 상세 테스트 결과</div>
            <table id="detail-table">
                <thead>
                    <tr>
                        <th class="sortable" data-sort-key="index">No.</th>
                        <th class="sortable" data-sort-key="testId">Test ID</th>
                        <th class="sortable" data-sort-key="group">Group / Test Name / File Name</th>
                        <th>Desc</th>
                        <th>Data</th>
                        <th>Result</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>
        <script>
        (function() {{
            const table = document.getElementById('detail-table');
            if (!table) return;
            const tbody = table.querySelector('tbody');
            const headers = table.querySelectorAll('th.sortable');
            const rows = Array.from(tbody.querySelectorAll('tr.test-row'));
            let currentSort = {{ key: 'index', direction: 'asc' }};
            
            function getValue(row, key) {{
                if (key === 'index') {{
                    return parseInt(row.dataset.index || '0', 10);
                }}
                if (key === 'testId') {{
                    return (row.dataset.testId || '').toLowerCase();
                }}
                if (key === 'group') {{
                    return (row.dataset.group || '').toLowerCase();
                }}
                return '';
            }}
            
            function applySort(key) {{
                let direction = 'asc';
                if (currentSort.key === key) {{
                    direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
                }}
                const sorted = rows.slice().sort((a, b) => {{
                    const aVal = getValue(a, key);
                    const bVal = getValue(b, key);
                    if (aVal === bVal) {{
                        return 0;
                    }}
                    if (key === 'index') {{
                        return direction === 'asc' ? aVal - bVal : bVal - aVal;
                    }}
                    return direction === 'asc'
                        ? aVal.localeCompare(bVal)
                        : bVal.localeCompare(aVal);
                }});
                
                sorted.forEach(row => {{
                    tbody.appendChild(row);
                    const detailId = row.dataset.detailId;
                    if (detailId) {{
                        const detailRow = document.getElementById(detailId);
                        if (detailRow) {{
                            tbody.appendChild(detailRow);
                        }}
                    }}
                }});
                rows.splice(0, rows.length, ...sorted);
                currentSort = {{ key, direction }};
                
                headers.forEach(header => header.classList.remove('sorted-asc', 'sorted-desc'));
                const activeHeader = Array.from(headers).find(h => h.dataset.sortKey === key);
                if (activeHeader) {{
                    activeHeader.classList.add(direction === 'asc' ? 'sorted-asc' : 'sorted-desc');
                }}
            }}
            
            headers.forEach(header => {{
                header.addEventListener('click', () => applySort(header.dataset.sortKey));
            }});
            
            const defaultHeader = Array.from(headers).find(h => h.dataset.sortKey === 'index');
            if (defaultHeader) {{
                defaultHeader.classList.add('sorted-asc');
            }}
        }})();
        (function() {{
            function setRowDataExpanded(detailRow, expanded) {{
                if (!detailRow) return;
                detailRow.hidden = !expanded;
                const detailId = detailRow.id;
                document.querySelectorAll('.row-data-toggle-btn[data-target="' + detailId + '"]').forEach(btn => {{
                    btn.setAttribute('aria-expanded', String(expanded));
                    btn.classList.toggle('active', expanded);
                    btn.textContent = expanded ? 'Hide' : 'View';
                }});
            }}
            
            document.querySelectorAll('.row-data-toggle-btn').forEach(button => {{
                button.addEventListener('click', () => {{
                    const targetId = button.getAttribute('data-target');
                    if (!targetId) return;
                    const detailRow = document.getElementById(targetId);
                    if (!detailRow) return;
                    const expanded = detailRow.hidden;
                    setRowDataExpanded(detailRow, expanded);
                }});
            }});
        }})();
        (function() {{
            const toggleButtons = document.querySelectorAll('.data-toggle-btn');
            toggleButtons.forEach(button => {{
                button.addEventListener('click', () => {{
                    const targetId = button.getAttribute('data-target');
                    if (!targetId) return;
                    const target = document.getElementById(targetId);
                    if (!target) return;
                    const isActive = target.classList.toggle('active');
                    button.setAttribute('aria-expanded', String(isActive));
                    button.textContent = isActive ? 'Hide' : 'Details';
                }});
            }});
        }})();
        </script>
        {footer_html}
    </div>

</body>
</html>
'''

        if split_by_group:
            # Index page keeps summary + group stats only (no detail table).
            html_content = re.sub(
                r'<div class="section">\s*<div class="section-title">📝 상세 테스트 결과</div>[\s\S]*?</table>\s*</div>',
                '',
                html_content,
                count=1,
            )

        if nav_html:
            html_content = re.sub(
                r'(<div class="header">[\s\S]*?</div>\s*)',
                r'\1' + nav_html + '\n        ',
                html_content,
                count=1,
            )

        if hide_group_stats:
            html_content = re.sub(
                r'<p class="group-hint">[\s\S]*?</p>\s*',
                '',
                html_content,
                count=0,
            )
            html_content = re.sub(
                r'<div class="section">\s*<div class="section-title">📊 그룹별 통계</div>[\s\S]*?</table>\s*</div>',
                '',
                html_content,
                count=1,
            )

        if not os.path.isdir(write_dir):
            os.makedirs(write_dir, exist_ok=True)
            
        try:
            report_path = os.path.join(write_dir, output_file)
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
        except Exception as e:
            print(f"Error generating report: {e}", file=sys.stderr)
            return ""

        if split_by_group:
            index_name = os.path.basename(report_path)
            for group_name in sorted(cases_by_group.keys()):
                group_cases = cases_by_group[group_name]
                group_file = group_file_map[group_name]
                group_gen = ReportGenerator(
                    group_cases,
                    self.vector_extractor,
                    title=f"{self.title} / {group_name}",
                    meta_info=None,
                    project_root=self.project_root,
                    log_source_name=self.log_source_name,
                    log_sha256=self.log_sha256,
                    log_source_path=None,
                    show_git_info=self.show_git_info,
                )
                group_gen.timestamp = self.timestamp
                group_gen.output_dir = self.output_dir
                group_gen.report_bundle_dir = write_dir
                group_path = group_gen.generate_html_report(
                    output_file=group_file,
                    split_by_group=False,
                    nav_html=(
                        f'<div class="nav-back"><a href="{html.escape(index_name, quote=True)}">'
                        f'&larr; Summary</a> &nbsp;|&nbsp; <strong>{html.escape(group_name)}</strong></div>'
                    ),
                    hide_group_stats=True,
                    write_dir=write_dir,
                )
                if group_path:
                    self.generated_group_reports.append(group_path)
        
        return report_path
