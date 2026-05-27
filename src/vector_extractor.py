import os
import re
import codecs

from typing import Optional, Dict, List, Any

class VectorExtractor:

    _INLINE_BYTE_HEX_RE = re.compile(r"0x[0-9A-Fa-f]{2}", re.IGNORECASE)
    
    def __init__(self, project_root: str = "."):
        self.project_root = project_root
        self.file_variables: Dict[str, Dict[str, Dict[str, Any]]] = {}  # file path -> {variable name -> data dict}
        self._load_all_vectors()  # Scan all C files (follow the path in the comment)
    
    def _load_all_vectors(self):
        """Extract variables from all C files in the project"""
        # Scan all .c files in the test directory
        for root, dirs, files in os.walk(os.path.join(self.project_root, 'test')):
            for file in files:
                if file.endswith('.c'):
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, self.project_root)
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        
                        array_pattern = re.compile(
                            r'(?:static\s+)?(?:const\s+)?uint8_t\s+(\w+)\s*\[\s*\d+\s*\]\s*=\s*\{([^}]+)\}',
                            re.MULTILINE | re.DOTALL
                        )
                        string_pattern = re.compile(
                            r'(?:static\s+)?(?:const\s+)?uint8_t\s+(\w+)\s*\[\s*\d+\s*\]\s*=\s*"((?:\\.|[^"\\])*)"',
                            re.MULTILINE | re.DOTALL
                        )
                        scalar_pattern = re.compile(
                            r'(?:static\s+)?(?:const\s+)?(u?int(?:8|16|32|64)_t)\s+(\w+)\s*(?!\[)\s*=\s*([^;]+);',
                            re.MULTILINE
                        )
                        
                        file_vars: Dict[str, Dict[str, Any]] = {}
                        for match in array_pattern.finditer(content):
                            var_name = match.group(1)
                            hex_data = match.group(2)
                            
                            hex_pattern = re.compile(r'0x[0-9a-fA-F]{2}')
                            hex_list = hex_pattern.findall(hex_data)
                            
                            if hex_list:
                                file_vars[var_name] = {
                                    'kind': 'array',
                                    'hex': hex_list
                                }
                        
                        for match in string_pattern.finditer(content):
                            var_name = match.group(1)
                            string_literal = match.group(2)
                            try:
                                decoded_str = codecs.decode(string_literal, 'unicode_escape')
                            except Exception:
                                decoded_str = string_literal
                            if decoded_str:
                                hex_list = [f'0x{ord(ch):02X}' for ch in decoded_str]
                                file_vars[var_name] = {
                                    'kind': 'string',
                                    'hex': hex_list,
                                    'literal': decoded_str
                                }
                        
                        for match in scalar_pattern.finditer(content):
                            type_name = match.group(1)
                            var_name = match.group(2)
                            raw_value = match.group(3).strip()
                            int_value = self._parse_int_literal(raw_value)
                            file_vars[var_name] = {
                                'kind': 'scalar',
                                'scalar': {
                                    'type': type_name,
                                    'raw': raw_value,
                                    'int': int_value
                                }
                            }
                        
                        if file_vars:
                            normalized_rel_path = relative_path.replace('\\', '/')
                            self.file_variables[normalized_rel_path] = file_vars
                    except Exception:
                        pass
    
    @staticmethod
    def _parse_int_literal(value_str: str) -> Optional[int]:
        token = value_str.strip()
        if not token:
            return None
        # Strip parentheses
        if token.startswith('(') and token.endswith(')'):
            token = token[1:-1].strip()
        # Remove casts e.g. (uint16_t)
        cast_pattern = re.compile(r'^\((?:u?int(?:8|16|32|64)_t)\)\s*')
        token = cast_pattern.sub('', token)
        # Remove suffixes U, UL, LL
        suffix_pattern = re.compile(r'(?:u|U|l|L)+$')
        token = suffix_pattern.sub('', token)
        try:
            return int(token, 0)
        except ValueError:
            return None
    
    def _get_var_entry(self, var_name: str, file_path: Optional[str]) -> Optional[Dict[str, Any]]:
        if not file_path:
            return None
        normalized_path = file_path.replace('\\', '/').lstrip('./')
        file_vars = self.file_variables.get(normalized_path)
        if not file_vars:
            return None
        return file_vars.get(var_name)

    @classmethod
    def parse_inline_byte_hex_tokens(cls, value_str: str) -> Optional[List[str]]:
        """로그 등에서 온 '0x6B 0xC1 ...' 또는 '0x6B, 0xC1' 형태만 허용 (바이트당 정확히 2 hex 자리).

        32비트 한 덩어리(0x000000c9)는 바이트 나열로 보지 않는다.
        """
        if not value_str:
            return None
        s = value_str.strip()
        if not s:
            return None
        tokens: List[str] = []
        last_end = 0
        for m in cls._INLINE_BYTE_HEX_RE.finditer(s):
            gap = s[last_end : m.start()]
            if gap and not re.fullmatch(r"[\s,]*", gap):
                return None
            raw = m.group(0)
            tokens.append(f"0x{int(raw, 16):02X}")
            last_end = m.end()
        tail = s[last_end:]
        if tail and not re.fullmatch(r"[\s,]*", tail):
            return None
        if len(tokens) < 2:
            return None
        return tokens

    def get_formatted_inline_byte_string(
        self, value_str: str, max_display: int = 16
    ) -> Optional[str]:
        """get_formatted_value와 동일한 줄바꿈 규칙으로 인라인 hex 바이트 나열을 포맷한다."""
        token_list = self.parse_inline_byte_hex_tokens(value_str)
        if not token_list:
            return None
        lines: List[str] = []
        for i in range(0, len(token_list), max_display):
            chunk = token_list[i : i + max_display]
            lines.append(", ".join(chunk))
        if len(lines) == 1:
            return lines[0]
        formatted = "\n".join(lines)
        return formatted.replace("\n", "<br/>")
    
    def get_formatted_value(self, var_name: str, max_display: int = 16, file_path: Optional[str] = None) -> Optional[str]:
        """Return the formatted string of the variable value
        
        Args:
            var_name: variable name (e.g. "test_aes_key")
            max_display: maximum number of bytes to display per line (default: 16)
            file_path: C file path (e.g. "test/common/test_vector.c") - required!
        
        Returns:
            Formatted string of the variable value or None
        """
        entry = self._get_var_entry(var_name, file_path)
        if not entry:
            return None
        hex_list = entry.get('hex')
        if not hex_list:
            return None
        
        total_bytes = len(hex_list)
        
        lines = []
        for i in range(0, total_bytes, max_display):
            chunk = hex_list[i:i+max_display]
            lines.append(', '.join(chunk))

        if len(lines) == 1:
            return lines[0]
        else:
            formatted = '\n'.join(lines)
            # HTML newline processing
            formatted_html = formatted.replace('\n', '<br/>')
            return formatted_html

    def get_literal_value(self, var_name: str, file_path: Optional[str] = None) -> Optional[str]:
        entry = self._get_var_entry(var_name, file_path)
        if not entry:
            return None
        literal = entry.get('literal')
        if isinstance(literal, str):
            return literal
        return None

    def get_scalar_value(self, var_name: str, file_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        entry = self._get_var_entry(var_name, file_path)
        if not entry:
            return None
        scalar_info = entry.get('scalar')
        if isinstance(scalar_info, dict):
            return scalar_info
        return None

    def is_string_variable(self, var_name: str, file_path: Optional[str] = None) -> bool:
        entry = self._get_var_entry(var_name, file_path)
        if not entry:
            return False
        return entry.get('kind') == 'string'