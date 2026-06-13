from __future__ import annotations

import py_compile
from pathlib import Path


def test_python_files_compile():
    project_root = Path(__file__).resolve().parents[1]
    files = [
        *sorted((project_root / "src" / "dw_agent").rglob("*.py")),
        *sorted((project_root / "mcp_server").rglob("*.py")),
    ]

    assert files
    for path in files:
        py_compile.compile(str(path), doraise=True)
