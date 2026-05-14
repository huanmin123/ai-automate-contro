param(
    [switch]$InstallDependencies,
    [switch]$SmokeTest,
    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-RepoPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $Path))
}

function Assert-UnderRepo {
    param([Parameter(Mandatory = $true)][string]$Path)
    $resolved = [System.IO.Path]::GetFullPath($Path)
    $repo = [System.IO.Path]::GetFullPath($RepoRoot)
    if (-not $resolved.StartsWith($repo, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝操作仓库外路径：$resolved"
    }
}

function Assert-UnderBuildTemp {
    param([Parameter(Mandatory = $true)][string]$Path)
    $resolved = [System.IO.Path]::GetFullPath($Path)
    $tempRoot = [System.IO.Path]::GetFullPath($BuildTempRoot)
    if (-not $resolved.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝操作 PyInstaller 临时目录外路径：$resolved"
    }
}

function Clear-DirectoryContents {
    param([Parameter(Mandatory = $true)][string]$Path)
    Assert-UnderRepo $Path
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    Get-ChildItem -LiteralPath $Path -Force | ForEach-Object {
        Assert-UnderRepo $_.FullName
        Remove-Item -LiteralPath $_.FullName -Recurse -Force
    }
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "命令执行失败：$FilePath $($Arguments -join ' ')"
    }
}

$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Set-Location $RepoRoot

if ($IsLinux) {
    throw "当前不支持 Linux 打包。Windows 可打包 .exe，Apple Silicon macOS 可打包 macOS 可执行文件。"
}
if (-not $IsWindows -and -not $IsMacOS) {
    throw "不支持当前操作系统。只支持 Windows 和 Apple Silicon macOS。"
}

$osArchitecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
if ($IsMacOS -and $osArchitecture -ne "arm64") {
    throw "macOS 打包目前只支持 Apple Silicon。当前架构：$osArchitecture"
}

$PlatformName = if ($IsWindows) { "windows-$osArchitecture" } else { "macos-arm64" }
$ExecutableBaseName = "aic"
$ExecutableFileName = if ($IsWindows) { "$ExecutableBaseName.exe" } else { $ExecutableBaseName }
$ExecutableCommandForDocs = if ($IsWindows) { ".\$ExecutableFileName" } else { "./$ExecutableFileName" }
$OutDir = Resolve-RepoPath "out"
$PackageDir = Join-Path $OutDir "ai-automate-contro"
$BuildTempRoot = [System.IO.Path]::GetFullPath((Join-Path ([System.IO.Path]::GetTempPath()) "ai-automate-contro-pyinstaller"))
$BuildDir = Join-Path $BuildTempRoot $PlatformName
$PyInstallerDistDir = Join-Path $BuildDir "dist"
$PyInstallerPackageDir = Join-Path $PyInstallerDistDir $ExecutableBaseName
$PyInstallerExecutablePath = Join-Path $PyInstallerPackageDir $ExecutableFileName
$SourceDir = Resolve-RepoPath "src"
$EntryPoint = Resolve-RepoPath "main.py"
$ExecutablePath = Join-Path $PackageDir $ExecutableFileName
$HandbookSourceDir = Resolve-RepoPath "handbook"
$PlanConfigPath = Join-Path $PackageDir "plan.config"
$PackageZipPath = Join-Path $OutDir "ai-automate-contro-$PlatformName.zip"
$ExistingPackagePlansConfigPath = Join-Path $PackageDir "plans\config.json"
$LocalPlansConfigBackupPath = $null

Assert-UnderRepo $OutDir
Assert-UnderRepo $PackageDir
Assert-UnderRepo $SourceDir
Assert-UnderRepo $EntryPoint
Assert-UnderRepo $HandbookSourceDir
Assert-UnderRepo $PlanConfigPath
Assert-UnderRepo $PackageZipPath

if (Test-Path -LiteralPath $ExistingPackagePlansConfigPath) {
    Assert-UnderRepo $ExistingPackagePlansConfigPath
    $LocalPlansConfigBackupPath = [System.IO.Path]::GetFullPath(
        (Join-Path ([System.IO.Path]::GetTempPath()) ("ai-automate-out-config-{0}.json" -f [System.Guid]::NewGuid().ToString("N")))
    )
    Copy-Item -LiteralPath $ExistingPackagePlansConfigPath -Destination $LocalPlansConfigBackupPath -Force
}

if ($Clean) {
    if (Test-Path -LiteralPath $BuildDir) {
        Assert-UnderBuildTemp $BuildDir
        Remove-Item -LiteralPath $BuildDir -Recurse -Force
    }
    if (Test-Path -LiteralPath $PackageDir) {
        Assert-UnderRepo $PackageDir
        try {
            Remove-Item -LiteralPath $PackageDir -Recurse -Force
        }
        catch {
            Write-Warning "分发目录正在被占用，将改为清空目录内容：$PackageDir"
            Clear-DirectoryContents $PackageDir
        }
    }
    if (Test-Path -LiteralPath $PackageZipPath) {
        Assert-UnderRepo $PackageZipPath
        Remove-Item -LiteralPath $PackageZipPath -Force
    }
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
New-Item -ItemType Directory -Force -Path $PackageDir | Out-Null
if (Test-Path -LiteralPath $BuildDir) {
    Assert-UnderBuildTemp $BuildDir
    Remove-Item -LiteralPath $BuildDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "PATH 中没有找到 python。"
}
if (-not (Get-Command rg -ErrorAction SilentlyContinue)) {
    throw "分发版 AI 终端必须安装 ripgrep (rg)。请在 PowerShell 7 执行：winget install --id BurntSushi.ripgrep.MSVC -e"
}

if ($InstallDependencies) {
    Invoke-Checked "python" @("-m", "pip", "install", "-e", ".[package]")
}

python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "未安装 PyInstaller。请执行：python -m pip install -e `".[package]`"，或用 -InstallDependencies 重新运行本脚本。"
}

$previousBrowsersPath = [Environment]::GetEnvironmentVariable("PLAYWRIGHT_BROWSERS_PATH", "Process")
try {
    $env:PLAYWRIGHT_BROWSERS_PATH = "0"
    Invoke-Checked "python" @("-m", "playwright", "install", "chromium")

    $pyinstallerArgs = @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--console",
        "--noupx",
        "--contents-directory", "_internal",
        "--name", $ExecutableBaseName,
        "--distpath", $PyInstallerDistDir,
        "--workpath", $BuildDir,
        "--specpath", $BuildDir,
        "--paths", $SourceDir,
        "--collect-data", "playwright",
        "--collect-data", "textual",
        "--collect-submodules", "langchain",
        "--collect-submodules", "langchain_openai",
        "--collect-submodules", "langgraph",
        "--collect-submodules", "langgraph.checkpoint.sqlite",
        "--collect-submodules", "rich",
        "--collect-submodules", "textual",
        $EntryPoint
    )
    Invoke-Checked "python" $pyinstallerArgs
}
finally {
    if ($null -eq $previousBrowsersPath) {
        Remove-Item Env:\PLAYWRIGHT_BROWSERS_PATH -ErrorAction SilentlyContinue
    }
    else {
        $env:PLAYWRIGHT_BROWSERS_PATH = $previousBrowsersPath
    }
}

if (-not (Test-Path -LiteralPath $PyInstallerExecutablePath)) {
    throw "打包已完成，但没有找到可执行文件：$PyInstallerExecutablePath"
}

Clear-DirectoryContents $PackageDir
Get-ChildItem -LiteralPath $PyInstallerPackageDir -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $PackageDir -Recurse -Force
}

if (-not (Test-Path -LiteralPath $ExecutablePath)) {
    throw "打包复制已完成，但没有找到可执行文件：$ExecutablePath"
}

if (-not $IsWindows) {
    chmod +x $ExecutablePath
}

$PackageHandbookDir = Join-Path $PackageDir "handbook"
if (Test-Path -LiteralPath $PackageHandbookDir) {
    Remove-Item -LiteralPath $PackageHandbookDir -Recurse -Force
}
Copy-Item -LiteralPath $HandbookSourceDir -Destination $PackageHandbookDir -Recurse -Force
$PackagePlansDir = Join-Path $PackageDir "plans"
$PackagePlansConfigPath = Join-Path $PackagePlansDir "config.json"
$PackageDemoPlanDir = Join-Path $PackagePlansDir "demo"
$PackageDemoDocsDir = Join-Path $PackageDemoPlanDir "docs"
$PackageDemoOutputDir = Join-Path $PackageDemoPlanDir "output"
New-Item -ItemType Directory -Force -Path $PackagePlansDir | Out-Null
New-Item -ItemType Directory -Force -Path $PackageDemoDocsDir | Out-Null
$planConfig = [ordered]@{
    handbook_path = "handbook"
    plan_roots = @("plans")
    default_ai_config_dir = "plans"
}
$planConfig | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $PlanConfigPath -Encoding UTF8
[ordered]@{
    description = "分发包 plans 的共享配置。需要使用 AI 终端或 ai action 时，请在这里添加 ai_services.default。"
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $PackagePlansConfigPath -Encoding UTF8
[ordered]@{
    name = "packaged-demo"
    variables = [ordered]@{}
    steps = @(
        [ordered]@{
            action = "print"
            message = "分发包 demo plan 可用。"
        }
    )
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $PackageDemoPlanDir "plan.json") -Encoding UTF8
$demoReadme = @"
# 分发包 demo

这个 plan 用于验证分发包是否可以正常校验和运行。

```powershell
$ExecutableCommandForDocs plan validate --file .\plans\demo\plan.json
$ExecutableCommandForDocs plan run --file .\plans\demo\plan.json --run-name demo-smoke
```
"@
$demoReadme | Set-Content -LiteralPath (Join-Path $PackageDemoDocsDir "README.md") -Encoding UTF8

if ($SmokeTest) {
    Push-Location $PackageDir
    try {
        Invoke-Checked $ExecutablePath @("self-check", "ai-stream")
        Invoke-Checked $ExecutablePath @("self-check", "textual-client")
        Invoke-Checked $ExecutablePath @("self-check", "ai-terminal")
        Invoke-Checked $ExecutablePath @("self-check", "runtime")
        Invoke-Checked $ExecutablePath @("tool", "check")
        Invoke-Checked $ExecutablePath @("plan", "validate", "--file", ".\plans\demo\plan.json")
        Invoke-Checked $ExecutablePath @("plan", "run", "--file", ".\plans\demo\plan.json", "--run-name", "demo-smoke")
    }
    finally {
        Pop-Location
    }
}

if (Test-Path -LiteralPath $PackageDemoOutputDir) {
    Assert-UnderRepo $PackageDemoOutputDir
    Remove-Item -LiteralPath $PackageDemoOutputDir -Recurse -Force
}

if (Test-Path -LiteralPath $PackageZipPath) {
    Remove-Item -LiteralPath $PackageZipPath -Force
}
Compress-Archive -LiteralPath $PackageDir -DestinationPath $PackageZipPath -Force

if ($SmokeTest) {
    $ZipSmokeDir = Join-Path $OutDir "zip-smoke"
    if (Test-Path -LiteralPath $ZipSmokeDir) {
        Remove-Item -LiteralPath $ZipSmokeDir -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $ZipSmokeDir | Out-Null
    Expand-Archive -LiteralPath $PackageZipPath -DestinationPath $ZipSmokeDir -Force
    $ExtractedPackageDir = Join-Path $ZipSmokeDir "ai-automate-contro"
    $ExtractedExecutablePath = Join-Path $ExtractedPackageDir $ExecutableFileName
    Push-Location $ExtractedPackageDir
    try {
        Invoke-Checked $ExtractedExecutablePath @("self-check", "ai-stream")
        Invoke-Checked $ExtractedExecutablePath @("self-check", "textual-client")
        Invoke-Checked $ExtractedExecutablePath @("self-check", "ai-terminal")
        Invoke-Checked $ExtractedExecutablePath @("self-check", "runtime")
        Invoke-Checked $ExtractedExecutablePath @("tool", "check")
        Invoke-Checked $ExtractedExecutablePath @("plan", "validate", "--file", ".\plans\demo\plan.json")
        Invoke-Checked $ExtractedExecutablePath @("plan", "run", "--file", ".\plans\demo\plan.json", "--run-name", "demo-smoke")
    }
    finally {
        Pop-Location
        Remove-Item -LiteralPath $ZipSmokeDir -Recurse -Force
    }
}

if ($null -ne $LocalPlansConfigBackupPath -and (Test-Path -LiteralPath $LocalPlansConfigBackupPath)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $PackagePlansConfigPath) | Out-Null
    Copy-Item -LiteralPath $LocalPlansConfigBackupPath -Destination $PackagePlansConfigPath -Force
    Write-Host "已恢复 out\\ai-automate-contro\\plans\\config.json 的本地配置；zip 内仍使用示例配置。"
}

if (Test-Path -LiteralPath $BuildDir) {
    Assert-UnderBuildTemp $BuildDir
    Remove-Item -LiteralPath $BuildDir -Recurse -Force
}
$BuildRoot = Split-Path -Parent $BuildDir
if ((Test-Path -LiteralPath $BuildRoot) -and -not (Get-ChildItem -LiteralPath $BuildRoot -Force)) {
    Assert-UnderBuildTemp $BuildRoot
    Remove-Item -LiteralPath $BuildRoot -Force
}

Write-Host "分发包可执行文件："
Write-Host $ExecutablePath
Write-Host "分发包 zip："
Write-Host $PackageZipPath
Write-Host "请从 out\ai-automate-contro 目录运行，或编辑 plan.config 指向其他 handbook/plans 位置。"
