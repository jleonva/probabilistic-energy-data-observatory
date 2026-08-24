$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
& "$repo\.venv\Scripts\python.exe" -m pytest
& "$repo\.venv\Scripts\python.exe" -m energy_observatory.cli run --root $repo

