$ErrorActionPreference = "Stop"

$venv = Join-Path $env:USERPROFILE ".cache\warehouse_agent_mvp_venv"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $python)) {
    uv venv --clear --python 3.12 $venv
}

uv pip install --python $python black isort ruff mypy pre-commit pytest

$env:PYTHONPATH = (Join-Path $PSScriptRoot "src") + ";" + $PSScriptRoot

function Invoke-Step {
    param([ScriptBlock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

Invoke-Step { & $python -m black . }
Invoke-Step { & $python -m isort . }
Invoke-Step { & $python -m ruff check . }
Invoke-Step { & $python -m mypy src mcp_server }
Invoke-Step { & $python -m pytest -q -p no:cacheprovider }
