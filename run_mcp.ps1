$ErrorActionPreference = "Stop"

$venv = Join-Path $env:USERPROFILE ".cache\warehouse_agent_mvp_venv"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $python)) {
    uv venv --clear --python 3.12 $venv
}

& $python -c "import streamlit, langgraph, langchain_openai, dotenv, mcp, pytest, sqlglot" 2>$null
if ($LASTEXITCODE -ne 0) {
    uv pip install --python $python langgraph streamlit langchain-openai python-dotenv mcp pytest sqlglot
}

$env:PYTHONPATH = (Join-Path $PSScriptRoot "src") + ";" + $PSScriptRoot
& $python -m mcp_server.server
