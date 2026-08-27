import re
from typing import List, Tuple, Optional

class DataParser:
    """Given/Expected Data Parsing ([src:file_path]variable_name rule supported)"""
    
    @staticmethod
    def parse_variables(data_str: str) -> List[Tuple[str, str, Optional[str]]]:
        """Parse data string into variable-by-variable
        
        Example 1: "key_id=5, key_data=test_key_256, size=32"
        → [("key_id", "5", None), ("key_data", "test_key_256", None), ("size", "32", None)]
        
        Example 2: "key_data=[src:test/common/test_vector.c]test_key_storage_aes"
        → [("key_data", "test_key_storage_aes", "test/common/test_vector.c")]
        """
        if data_str == '-':
            return []

        items = []
        chunks = [data_str]
        if "\n" in data_str:
            chunks = [line.strip() for line in data_str.splitlines() if line.strip()]

        for chunk in chunks:
            items.extend(DataParser._parse_chunk(chunk))
        return items

    @staticmethod
    def _parse_chunk(data_str: str) -> List[Tuple[str, str, Optional[str]]]:
        items = []

        # 다음 `key=` 앞에서만 분리한다. 키에 공백이 있어도 되고
        # (`Start ESF_RET=16`), hex 덤프의 `0x76, 0x49` 콤마는 값으로 유지한다.
        parts = re.split(r",\s*(?=[^=,]+=)", data_str)

        for part in parts:
            part = part.strip()
            if '=' in part:
                key, val = part.split('=', 1)
                key = key.strip()
                val = val.strip()
                
                src_pattern = re.compile(r'\[src:(.+?)\](.+)')
                src_match = src_pattern.match(val)
                
                if src_match:
                    file_path = src_match.group(1)
                    var_name = src_match.group(2)
                    items.append((key, var_name, file_path))
                else:
                    items.extend(DataParser._split_mashed_value(key, val))
            else:
                items.append(('value', part, None))
        
        return items

    @staticmethod
    def _split_mashed_value(key: str, val: str):
        """값이 `16, Start ESF_ERR_CODE=1, Start ESF_STATE=3`처럼 다음 키를 포함하면 분리한다."""
        if not val or not re.search(r",\s*[^=,]+=", val):
            return [(key, val, None)]
        blob = f"{key}={val}"
        parts = re.split(r",\s*(?=[^=,]+=)", blob)
        if len(parts) <= 1:
            return [(key, val, None)]
        out = []
        for part in parts:
            part = part.strip()
            if '=' not in part:
                continue
            sub_key, sub_val = part.split('=', 1)
            out.append((sub_key.strip(), sub_val.strip(), None))
        return out or [(key, val, None)]