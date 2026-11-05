$ErrorActionPreference = 'Stop'
$psqlPath = 'C:\Program Files\PostgreSQL\18\bin\psql.exe'
$pythonPath = 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$sqlPath = Join-Path $PSScriptRoot 'landmark_import_stage\import.sql'
$manifestPath = Join-Path $PSScriptRoot 'landmark_import_stage\manifest.json'
if (Test-Path -LiteralPath $sqlPath) {
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($manifest.extraction_profile -ne 'broad_100gb_v1') {
        throw 'An older selective subset is staged. Ask Codex to migrate it before importing.'
    }
}
if (-not (Test-Path -LiteralPath $sqlPath)) {
    Write-Host 'Preparing the selective subset. The large compressed files must be scanned; progress will appear below.'
    & $pythonPath -u (Join-Path $PSScriptRoot 'prepare_landmark_import.py') --restart-preparation
    if ($LASTEXITCODE -ne 0) {
        throw 'Subset preparation failed. No database import was attempted. Report the error to Codex.'
    }
}
& $pythonPath -u (Join-Path $PSScriptRoot 'import_sql_incremental.py')
if ($LASTEXITCODE -ne 0) { throw 'Could not prepare resumable import SQL. No database import attempted.' }
$drive = Get-PSDrive -Name ([IO.Path]::GetPathRoot($PSScriptRoot).Substring(0,1))
if ($drive.Free -lt 10000000000) {
    throw 'Less than 10 GB free for temporary work. Report available space to Codex.'
}
Write-Host 'Importing into landmark_research / landmark_mimic48. Existing schemas will not be overwritten.'
Write-Host 'Enter the PostgreSQL password locally. It will not be saved.'
Write-Host 'Each table is verified and committed before its staged CSV is deleted. A rerun skips committed tables.'
& $psqlPath -X -W -h localhost -p 5432 -U postgres -d landmark_research -v ON_ERROR_STOP=1 -f $sqlPath
if ($LASTEXITCODE -ne 0) {
    throw 'Import failed. Preserve the error message and report it to Codex. Do not delete any existing schema.'
}
Write-Host 'Selective import completed. Report the final table size and cohort counts to Codex.'
