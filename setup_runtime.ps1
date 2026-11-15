<#
    安装 zhtrans 的本地翻译运行时（Node + MTranServer + en->zh-Hans 模型）。

    用法：
      powershell -ExecutionPolicy Bypass -File .\setup_runtime.ps1 -FromPath 'C:\path\to\vendor'
      powershell -ExecutionPolicy Bypass -File .\setup_runtime.ps1 -Url 'https://.../runtime.zip'
      powershell -ExecutionPolicy Bypass -File .\setup_runtime.ps1 -Force

    默认安装到项目根目录的 vendor/（该目录已被 .gitignore 忽略）。
#>
param(
    [string]$FromPath = "",
    [string]$Url = "",
    [string]$Destination = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Destination) {
    $Destination = Join-Path $root "vendor"
}
$metaPath = Join-Path $root "runtime.json"

$meta = $null
if (Test-Path -LiteralPath $metaPath) {
    $meta = Get-Content -LiteralPath $metaPath -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Test-Runtime {
    param([string]$Dir)
    if (-not (Test-Path -LiteralPath $Dir)) {
        return $false
    }
    $checks = @(
        "node\node.exe",
        "mtranserver\node_modules\mtranserver\dist\main.js",
        "mtranserver-data\models\en_zh-Hans",
        "mtranserver-data\config"
    )
    foreach ($rel in $checks) {
        if (-not (Test-Path -LiteralPath (Join-Path $Dir $rel))) {
            return $false
        }
    }
    return $true
}

if ((Test-Runtime $Destination) -and (-not $Force)) {
    Write-Host "[ok] Runtime already installed: $Destination"
    exit 0
}

if ($FromPath) {
    if (-not (Test-Runtime $FromPath)) {
        throw "Not a valid runtime directory: $FromPath"
    }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Copy-Item -Path (Join-Path $FromPath "*") -Destination $Destination -Recurse -Force
    if (-not (Test-Runtime $Destination)) {
        throw "Copy finished but the runtime is incomplete."
    }
    Write-Host "[ok] Runtime copied to: $Destination"
    exit 0
}

if (-not $Url -and $meta -and $meta.url) {
    $Url = [string]$meta.url
}
if (-not $Url) {
    throw "No runtime source. Use -FromPath <dir> or -Url <zip>, or set 'url' in runtime.json."
}

$archiveName = "simple-translation-runtime.zip"
if ($meta -and $meta.archive) {
    $archiveName = [string]$meta.archive
}
$zip = Join-Path $env:TEMP $archiveName

Write-Host "[..] Downloading $Url"
Invoke-WebRequest -Uri $Url -OutFile $zip -UseBasicParsing

if ($meta -and $meta.sha256) {
    $actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne ([string]$meta.sha256).ToLower()) {
        throw "SHA256 mismatch: expected $($meta.sha256), got $actual"
    }
    Write-Host "[ok] SHA256 verified"
}

$tmp = Join-Path $env:TEMP ("simple-translation-runtime-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

if (Get-Command tar.exe -ErrorAction SilentlyContinue) {
    & tar.exe -x -f $zip -C $tmp
} else {
    Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force
}

$sourceRoot = $null
if (Test-Runtime $tmp) {
    $sourceRoot = $tmp
} else {
    $node = Get-ChildItem -Path $tmp -Recurse -Filter node.exe -File -ErrorAction SilentlyContinue |
        Where-Object { $_.DirectoryName -match '[\\/]node$' } |
        Select-Object -First 1
    if ($node) {
        $sourceRoot = Split-Path -Parent $node.DirectoryName
    }
}
if (-not $sourceRoot) {
    throw "Could not locate the runtime inside the archive."
}

New-Item -ItemType Directory -Force -Path $Destination | Out-Null
Copy-Item -Path (Join-Path $sourceRoot "*") -Destination $Destination -Recurse -Force
if (-not (Test-Runtime $Destination)) {
    throw "Extracted runtime is incomplete."
}

Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "[ok] Runtime installed to: $Destination"
