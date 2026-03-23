import os
import json
from typing import Union, List, Dict

def load_meta_info(meta_arg: str) -> Union[Dict[str, str], List[Dict[str, str]]]:
    meta_info: Union[Dict[str, str], List[Dict[str, str]]] = {}
    if not meta_arg:
        return meta_info
    
    meta_source = meta_arg
    if os.path.isfile(meta_source):
        try:
            with open(meta_source, 'r', encoding='utf-8') as f:
                meta_source = f.read()
        except OSError as e:
            print(f"[!] Meta info file not found: {e}")
            meta_source = ""
    
    if not meta_source:
        return meta_info
    
    try:
        parsed_meta = json.loads(meta_source)
        if isinstance(parsed_meta, dict):
            meta_info = parsed_meta
        elif isinstance(parsed_meta, list):
            meta_list = [item for item in parsed_meta if isinstance(item, dict)]
            if meta_list:
                meta_info = meta_list
            else:
                print("[!] No usable object in meta info JSON array.")
        else:
            print("[!] Meta info JSON must be an object or an array of objects.")
    except json.JSONDecodeError as e:
        print(f"[!] Meta info JSON parsing failed: {e}")
    
    return meta_info