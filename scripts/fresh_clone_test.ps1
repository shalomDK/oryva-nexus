# Fresh-clone dry run: copy the project (no git history, no caches, no generated full data) to a temp dir,
# create a new virtualenv, follow the README (install -> generate -> validate -> tests -> load-sql) and check that the
# freshly generated starter export is byte-identical (SHA-256) to the committed data/starter.
param([string]$Work = "$env:TEMP\oryva_fresh_clone")
$ErrorActionPreference = "Continue"
$src = Split-Path -Parent $PSScriptRoot
if (Test-Path $Work) { Remove-Item -Recurse -Force $Work }
New-Item -ItemType Directory $Work | Out-Null
robocopy $src $Work /E /XD .git .venv __pycache__ .pytest_cache _scratch full "*.egg-info" /XF "*.pyc" "*.sqlite" /NFL /NDL /NJH /NJS | Out-Null
Set-Location $Work
python -m venv .venv 2>&1 | Out-Null
& .\.venv\Scripts\python.exe -m pip install -q -e ".[dev]" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
$py = ".\.venv\Scripts\python.exe"
& $py -m oryva generate --profile starter --out data/starter_fresh 2>&1 | Out-File gen.log
if ($LASTEXITCODE -ne 0) { throw "generate failed" }
& $py -m oryva validate --data-dir data/starter_fresh 2>&1 | Out-File val.log
if ($LASTEXITCODE -ne 0) { throw "validate failed" }
& $py -m oryva load-sql --data-dir data/starter_fresh --db fresh.sqlite
if ($LASTEXITCODE -ne 0) { throw "load-sql failed" }
& $py -m pytest -q -p no:cacheprovider 2>&1 | Out-File pytest.log
$pt = $LASTEXITCODE
$a = (Get-Content data/starter/manifest.json -Raw | ConvertFrom-Json).files
$b = (Get-Content data/starter_fresh/manifest.json -Raw | ConvertFrom-Json).files
$diff = @()
foreach ($p in $a.PSObject.Properties) { if ($b.$($p.Name).sha256 -ne $p.Value.sha256) { $diff += $p.Name } }
"files compared: $(($a.PSObject.Properties | Measure-Object).Count); differing: $($diff.Count)"
"pytest exit: $pt"; Get-Content pytest.log | Select-Object -Last 2
if ($diff.Count -ne 0 -or $pt -ne 0) { $diff | Select-Object -First 5; exit 1 }
"FRESH CLONE OK"

