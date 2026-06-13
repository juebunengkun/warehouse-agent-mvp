$ErrorActionPreference = "Stop"

$venv = Join-Path $env:USERPROFILE ".cache\warehouse_agent_mvp_venv"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $python)) {
    uv venv --clear --python 3.12 $venv
}

$env:PYTHONPATH = (Join-Path $PSScriptRoot "src") + ";" + $PSScriptRoot

& $python -c @"
from pathlib import Path
from dw_agent.graph import run_agent

requirement = Path('examples/sales_channel_daily.md').read_text(encoding='utf-8')
result = run_agent(requirement)

print('parser_source=' + result['parsed'].get('parser_source', ''))
print('llm_status=' + result.get('llm_diagnostics', {}).get('status', 'missing'))
print('llm_error=' + result.get('llm_diagnostics', {}).get('error_type', ''))
print('reuse=' + result['reuse_decision'].get('decision', '') + ':' + str(result['reuse_decision'].get('table', '')))
print('sql_validation=' + str(result['sql_validation'].get('passed')))
print('sql_style=' + str(result['sql_style_review'].get('passed')))
print('business_process=' + result['modeling_strategy'].get('business_process', ''))
"@
