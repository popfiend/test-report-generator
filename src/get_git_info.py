import subprocess
import sys
from typing import Optional, Tuple

def get_git_info(project_root: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    commit = None
    branch = None
    tag = None
    
    if not project_root:
        return commit, branch, tag
    
    try:
        commit = subprocess.check_output(
            ['git', '-C', project_root, 'rev-parse', 'HEAD'],
            stderr=subprocess.DEVNULL,
            text=True
        ).strip()
    except Exception:
        commit = None
    
    try:
        branch = subprocess.check_output(
            ['git', '-C', project_root, 'rev-parse', '--abbrev-ref', 'HEAD'],
            stderr=subprocess.DEVNULL,
            text=True
        ).strip()
    except Exception:
        branch = None
    
    if commit:
        try:
            tag = subprocess.check_output(
                ['git', '-C', project_root, 'describe', '--tags', '--exact-match'],
                stderr=subprocess.DEVNULL,
                text=True
            ).strip()
        except Exception:
            tag = None
    
    return commit, branch, tag
