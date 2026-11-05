$ErrorActionPreference='Stop'
$psqlPath='C:\Program Files\PostgreSQL\18\bin\psql.exe'
$sqlPath=Join-Path $PSScriptRoot '18_pruning_harmonization_audit_v2.sql'
Write-Host 'Read-only audit of six laboratory predictors in imported source tables. No model fitting or database changes.'
Write-Host 'Enter the postgres password locally. Only aggregate counts are exported.'
& $psqlPath -X -W -h localhost -p 5432 -U postgres -d landmark_research -v ON_ERROR_STOP=1 -f $sqlPath
if($LASTEXITCODE -ne 0){throw 'Read-only audit failed; preserve the error and report it.'}
$folder=Join-Path $PSScriptRoot 'model_results/pruning_focused_amendment_2026_10_29_v1'
foreach($name in @('MIMIC_harmonization_funnel.csv','eICU_harmonization_funnel.csv')){
 Write-Host $name
 Get-Content -LiteralPath (Join-Path $folder $name)
}
Write-Host 'Send these aggregate counts only. This audit cannot see records excluded before import or infer a clinical reason for missingness.'

