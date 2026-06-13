$ErrorActionPreference = "Stop"

$venv = Join-Path $env:USERPROFILE ".cache\warehouse_agent_mvp_venv"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $python)) {
    uv venv --clear --python 3.12 $venv
}

& $python -c "import streamlit, langgraph, langchain_openai, dotenv, mcp, sqlglot" 2>$null
if ($LASTEXITCODE -ne 0) {
    uv pip install --python $python langgraph streamlit langchain-openai python-dotenv mcp pytest sqlglot
}

$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
& $python -m streamlit run (Join-Path $PSScriptRoot "app.py") --server.headless=true --server.address=127.0.0.1 --server.port=8501 --browser.gatherUsageStats=false
