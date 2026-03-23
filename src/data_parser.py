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
        
        parts = data_str.split(',')
        
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
                    items.append((key, val, None))
            else:
                items.append(('value', part, None))
        
        return items