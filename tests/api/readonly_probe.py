"""Private mount namespace: production probe against an actual RO tmpfs."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

path = Path(__file__).resolve().parents[2] / "src/daesingo/api/storage.py"
spec = importlib.util.spec_from_file_location("storage_probe", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory(prefix="rt08a-readonly-") as directory:
    root = Path(directory)
    subprocess.run(["mount", "-t", "tmpfs", "-o", "ro,size=1m", "tmpfs", str(root)], check=True)
    try:
        readonly = bool(os.statvfs(root).f_flag & os.ST_RDONLY)
        assert readonly, "acceptance requires an actual read-only mount"
        print(json.dumps({"readonly": readonly, "available": module.storage_available(root)}))
        assert list(root.iterdir()) == [], "storage probe wrote files"
    finally:
        subprocess.run(["umount", str(root)], check=True)
