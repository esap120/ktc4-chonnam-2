"""Metadata-only mount probe (B-H2); no writes or path logging."""
import os
from pathlib import Path


def storage_available(root: Path) -> bool:
    try:
        if not root.is_dir() or not os.access(root, os.W_OK):
            return False
        if hasattr(os, "statvfs"):
            return not bool(os.statvfs(root).f_flag & os.ST_RDONLY)
        # Windows has no statvfs; directory/access checks still apply.
        return True
    except OSError:
        return False
