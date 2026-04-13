param(
  [Parameter(Mandatory = $true)]
  [string]$InputPath,

  [Parameter(Mandatory = $false)]
  [string]$OutputPath
)

$ErrorActionPreference = "Stop"

$resolvedInput = Resolve-Path -LiteralPath $InputPath | Select-Object -ExpandProperty Path
$configPath = Join-Path $PSScriptRoot "..\.markdownlint.json"
$configPath = Resolve-Path -LiteralPath $configPath | Select-Object -ExpandProperty Path

Write-Output "[1/3] Running Prettier on $resolvedInput"
& npx.cmd --yes prettier --write $resolvedInput | Out-Null

Write-Output "[2/3] Running markdownlint-cli2 --fix"
& npx.cmd --yes markdownlint-cli2 --fix --config $configPath $resolvedInput | Out-Null

Write-Output "[3/3] Verifying markdownlint-cli2"
$verify = & npx.cmd --yes markdownlint-cli2 --config $configPath $resolvedInput 2>&1 | Out-String
if ($verify -notmatch "Summary:\s+0 error\(s\)") {
  Write-Error "Lint verification failed.`n$verify"
}

if ($OutputPath) {
  Copy-Item -LiteralPath $resolvedInput -Destination $OutputPath -Force
  Write-Output "Cleaned output copied to $OutputPath"
}

Write-Output "Formatting cleanup complete."
