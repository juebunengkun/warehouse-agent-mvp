$ErrorActionPreference = "Stop"

$venv = Join-Path $env:USERPROFILE ".cache\warehouse_agent_mvp_venv"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $python)) {
    uv venv --clear --python 3.12 $venv
}

& $python -c "import streamlit, langgraph, langchain_openai, dotenv, mcp, pytest" 2>$null
if ($LASTEXITCODE -ne 0) {
    uv pip install --python $python langgraph streamlit langchain-openai python-dotenv mcp pytest
}

$env:PYTHONPATH = (Join-Path $PSScriptRoot "src") + ";" + $PSScriptRoot
$env:WAREHOUSE_AGENT_USE_LLM = "false"
& $python -m pytest -q -p no:cacheprovider
