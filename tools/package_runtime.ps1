<#
    把本地 vendor 运行时打包成 zip，便于作为 GitHub Release 附件发布。

    用法：
      powershell -ExecutionPolicy Bypass -File .\tools\package_runtime.ps1
      powershell -ExecutionPolicy Bypass -File .\tools\package_runtime.ps1 -UpdateMetadata
#>
param(
    [string]$Source = "",
    [string]$Output = "",
    [switch]$UpdateMetadata
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $Source) {
    $Source = Join-Path $projectRoot "vendor"
}
if (-not $Output) {
    $dist = Join-Path $projectRoot "dist"
    New-Item -ItemType Directory -Force -Path $dist | Out-Null
    $Output = Join-Path $dist "simple-translation-runtime-win64.zip"
}

foreach ($rel in @(
    "node\node.exe",
    "mtranserver\node_modules\mtranserver\dist\main.js",
    "mtranserver-data\models\en_zh-Hans",
    "mtranserver-data\config"
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $Source $rel))) {
        throw "Invalid runtime source (missing $rel): $Source"
    }
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Output) | Out-Null
if (Test-Path -LiteralPath $Output) {
    Remove-Item -LiteralPath $Output -Force
}

Write-Host "[..] Packaging $Source -> $Output"
if (Get-Command tar.exe -ErrorAction SilentlyContinue) {
    & tar.exe -a -c -f $Output -C $Source .
} else {
    Compress-Archive -Path (Join-Path $Source "*") -DestinationPath $Output -Force
}

$item = Get-Item -LiteralPath $Output
$hash = (Get-FileHash -LiteralPath $Output -Algorithm SHA256).Hash.ToLower()
Write-Host ("[ok] {0} ({1:N1} MB)" -f $Output, ($item.Length / 1MB))
Write-Host ("[ok] SHA256 {0}" -f $hash)

if ($UpdateMetadata) {
    $metaPath = Join-Path $projectRoot "runtime.json"
    $meta = Get-Content -LiteralPath $metaPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $meta.archive = $item.Name
    $meta.sha256 = $hash
    $meta.size = $item.Length
    $json = $meta | ConvertTo-Json -Depth 10
    [IO.File]::WriteAllText($metaPath, $json, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "[ok] runtime.json updated"
}
