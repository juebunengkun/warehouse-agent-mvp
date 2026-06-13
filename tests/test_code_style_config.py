from __future__ import annotations

import tomllib
from pathlib import Path


def test_code_style_config_exists():
    project_root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    dev_dependencies = "\n".join(pyproject["dependency-groups"]["dev"])

    for package in ["ruff", "black", "isort", "mypy", "pre-commit"]:
        assert package in dev_dependencies

    assert "ruff" in pyproject["tool"]
    assert "black" in pyproject["tool"]
    assert "isort" in pyproject["tool"]
    assert "mypy" in pyproject["tool"]
    assert (project_root / ".pre-commit-config.yaml").exists()
    assert (project_root / "docs" / "code_style.md").exists()
    assert (project_root / "docs" / "sql_style.md").exists()
    assert (project_root / "docs" / "modeling_rules.md").exists()
    assert (project_root / "docs" / "production_gap.md").exists()
