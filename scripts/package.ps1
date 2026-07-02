param(
    [switch]$InstallDependencies,
    [switch]$SmokeTest,
    [string]$PythonPath,
    [switch]$SkipZip,
    [switch]$NoProcessCleanup,
    [switch]$ProbeOnly,
    [ValidateSet("None", "Cleanup", "DependencyCheck", "PlaywrightInstall", "PyInstaller", "CopyPackage")]
    [string]$StopAfter = "None",
    [switch]$BundleBrowser,
    [switch]$SkipPlaywrightInstall,
    [string]$OutputSuffix = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-RepoPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $Path))
}

function Assert-UnderRepo {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-PathUnderRoot -Path $Path -Root $RepoRoot)) {
        $resolved = [System.IO.Path]::GetFullPath($Path)
        throw "拒绝操作仓库外路径：$resolved"
    }
}

function Assert-UnderBuildTemp {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-PathUnderRoot -Path $Path -Root $BuildTempRoot)) {
        $resolved = [System.IO.Path]::GetFullPath($Path)
        throw "拒绝操作 PyInstaller 临时目录外路径：$resolved"
    }
}

function Test-PathUnderRoot {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Root
    )
    $comparison = if ($IsWindows) { [System.StringComparison]::OrdinalIgnoreCase } else { [System.StringComparison]::Ordinal }
    $resolved = [System.IO.Path]::GetFullPath($Path).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $resolvedRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    if ($resolved.Equals($resolvedRoot, $comparison)) {
        return $true
    }
    $directoryPrefix = $resolvedRoot + [System.IO.Path]::DirectorySeparatorChar
    if ($resolved.StartsWith($directoryPrefix, $comparison)) {
        return $true
    }
    if ([System.IO.Path]::AltDirectorySeparatorChar -ne [System.IO.Path]::DirectorySeparatorChar) {
        $alternatePrefix = $resolvedRoot + [System.IO.Path]::AltDirectorySeparatorChar
        return $resolved.StartsWith($alternatePrefix, $comparison)
    }
    return $false
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
    Write-PackageCheckpoint ("RUN " + $FilePath + " " + ($Arguments -join " "))
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "命令执行失败：$FilePath $($Arguments -join ' ')"
    }
}

function Write-PackageCheckpoint {
    param([Parameter(Mandatory = $true)][string]$Message)
    $line = "{0:yyyy-MM-dd HH:mm:ss.fff} {1}" -f (Get-Date), $Message
    Write-Host $line
    if ((Get-Variable -Name PackageLogPath -Scope Script -ErrorAction SilentlyContinue) -and $script:PackageLogPath) {
        Add-Content -LiteralPath $script:PackageLogPath -Value $line -Encoding UTF8
    }
}

function Invoke-PackagedBrowserSmoke {
    param([Parameter(Mandatory = $true)][string]$FilePath)
    $browserSmokeDir = Join-Path ([System.IO.Path]::GetTempPath()) ("ai-automate-browser-smoke-{0}" -f [System.Guid]::NewGuid().ToString("N"))
    $resourcesDir = Join-Path $browserSmokeDir "resources"
    try {
        New-Item -ItemType Directory -Force -Path $resourcesDir | Out-Null
        @"
<!doctype html>
<html><head><meta charset="utf-8"><title>Packaged Browser Smoke</title></head>
<body><h1 id="title">Packaged Browser Smoke</h1></body></html>
"@ | Set-Content -LiteralPath (Join-Path $resourcesDir "demo.html") -Encoding UTF8
        @"
{
  "name": "packaged-browser-smoke",
  "automation_type": "browser",
  "variables": {
    "expected_title": "Packaged Browser Smoke"
  },
  "steps": [
    {
      "action": "open_browser",
      "name": "demo",
      "headed": false
    },
    {
      "action": "navigate",
      "browser": "demo",
      "url": "{{resources_file_url}}/demo.html",
      "type": "goto"
    },
    {
      "action": "assert",
      "browser": "demo",
      "selector": "#title",
      "expected": "{{expected_title}}",
      "type": "text"
    }
  ]
}
"@ | Set-Content -LiteralPath (Join-Path $browserSmokeDir "plan.json") -Encoding UTF8
        Invoke-Checked $FilePath @("validate", "--file", (Join-Path $browserSmokeDir "plan.json"))
        Invoke-Checked $FilePath @("run", "--file", (Join-Path $browserSmokeDir "plan.json"), "--run-name", "browser-smoke")
    }
    finally {
        if (Test-Path -LiteralPath $browserSmokeDir) {
            Remove-Item -LiteralPath $browserSmokeDir -Recurse -Force
        }
    }
}

function Stop-ExistingPackageProcesses {
    if ($IsWindows) {
        $processes = Get-CimInstance Win32_Process | Where-Object {
            $commandLine = [string]$_.CommandLine
            $name = [string]$_.Name
            $executablePath = [string]$_.ExecutablePath
            $pidValue = [int]$_.ProcessId
            if ($pidValue -eq $PID) {
                return $false
            }
            return (
                $executablePath.Equals($ExecutablePath, [System.StringComparison]::OrdinalIgnoreCase) -or
                $executablePath.Equals($CPlanExecutablePath, [System.StringComparison]::OrdinalIgnoreCase) -or
                $executablePath.StartsWith($PackageDir + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase) -or
                $commandLine.Contains($ExecutablePath, [System.StringComparison]::OrdinalIgnoreCase) -or
                $commandLine.Contains($CPlanExecutablePath, [System.StringComparison]::OrdinalIgnoreCase) -or
                $commandLine.Contains($PackageDir, [System.StringComparison]::OrdinalIgnoreCase) -or
                (
                    $commandLine.Contains("package.ps1", [System.StringComparison]::OrdinalIgnoreCase) -and
                    $commandLine.Contains($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)
                ) -or
                (
                    $commandLine.Contains("PyInstaller", [System.StringComparison]::OrdinalIgnoreCase) -and
                    $commandLine.Contains($BuildTempRoot, [System.StringComparison]::OrdinalIgnoreCase)
                )
            )
        }
        $ids = @($processes | ForEach-Object { [int]$_.ProcessId } | Sort-Object -Unique)
        if ($ids.Count -eq 0) {
            return
        }
        Write-Host ("停止旧打包/分发包进程：" + ($ids -join ", "))
        foreach ($id in $ids) {
            Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 1
        return
    }

    $rows = & ps -axo pid=,command=
    $ids = @()
    foreach ($row in $rows) {
        $line = ([string]$row).Trim()
        if (-not $line) {
            continue
        }
        $parts = $line -split "\s+", 2
        if ($parts.Count -lt 2) {
            continue
        }
        $pidValue = 0
        if (-not [int]::TryParse($parts[0], [ref]$pidValue)) {
            continue
        }
        if ($pidValue -eq $PID) {
            continue
        }
        $commandLine = $parts[1]
        if (
            $commandLine.Contains($ExecutablePath, [System.StringComparison]::Ordinal) -or
            $commandLine.Contains($CPlanExecutablePath, [System.StringComparison]::Ordinal) -or
            $commandLine.Contains("$PackageDir/", [System.StringComparison]::Ordinal) -or
            $commandLine.Contains("./$ExecutableFileName", [System.StringComparison]::Ordinal) -or
            $commandLine.Contains("./$CPlanExecutableFileName", [System.StringComparison]::Ordinal) -or
            (
                $commandLine.Contains("package.ps1", [System.StringComparison]::Ordinal) -and
                $commandLine.Contains($RepoRoot, [System.StringComparison]::Ordinal)
            ) -or
            (
                $commandLine.Contains("PyInstaller", [System.StringComparison]::Ordinal) -and
                $commandLine.Contains($BuildTempRoot, [System.StringComparison]::Ordinal)
            )
        ) {
            $ids += $pidValue
        }
    }
    $ids = @($ids | Sort-Object -Unique)
    if ($ids.Count -eq 0) {
        return
    }
    Write-Host ("停止旧打包/分发包进程：" + ($ids -join ", "))
    foreach ($id in $ids) {
        Stop-Process -Id $id -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
    foreach ($id in $ids) {
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
    }
}

function Remove-PackagePath {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    try {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        return
    }
    catch {
        if (-not $NoProcessCleanup) {
            Stop-ExistingPackageProcesses
        }
        Start-Sleep -Seconds 1
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
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
if ($OutputSuffix -and $OutputSuffix -notmatch "^[A-Za-z0-9][A-Za-z0-9._-]*$") {
    throw "OutputSuffix 只能包含字母、数字、点、下划线或短横线，并且必须以字母或数字开头：$OutputSuffix"
}
$PackageName = if ($OutputSuffix) { "ai-automate-contro-$OutputSuffix" } else { "ai-automate-contro" }
$BuildTempRootName = if ($OutputSuffix) { "ai-automate-contro-pyinstaller-$OutputSuffix" } else { "ai-automate-contro-pyinstaller" }
$PackageLogFileName = if ($OutputSuffix) { "package-last-$OutputSuffix.log" } else { "package-last.log" }
$ExecutableBaseName = "aic"
$CPlanExecutableBaseName = "cplan"
$ExecutableFileName = if ($IsWindows) { "$ExecutableBaseName.exe" } else { $ExecutableBaseName }
$CPlanExecutableFileName = if ($IsWindows) { "$CPlanExecutableBaseName.exe" } else { $CPlanExecutableBaseName }
$ExecutableCommandForDocs = if ($IsWindows) { ".\$ExecutableFileName" } else { "./$ExecutableFileName" }
$CPlanExecutableCommandForDocs = if ($IsWindows) { ".\$CPlanExecutableFileName" } else { "./$CPlanExecutableFileName" }
$OutDir = Resolve-RepoPath "out"
$PackageDir = Join-Path $OutDir $PackageName
$BuildTempRoot = [System.IO.Path]::GetFullPath((Join-Path ([System.IO.Path]::GetTempPath()) $BuildTempRootName))
$BuildDir = Join-Path $BuildTempRoot $PlatformName
$PyInstallerDistDir = Join-Path $BuildDir "dist"
$PyInstallerPackageDir = Join-Path $PyInstallerDistDir $ExecutableBaseName
$PyInstallerExecutablePath = Join-Path $PyInstallerPackageDir $ExecutableFileName
$SourceDir = Resolve-RepoPath "src"
$EntryPoint = Resolve-RepoPath "main.py"
$ExecutablePath = Join-Path $PackageDir $ExecutableFileName
$CPlanExecutablePath = Join-Path $PackageDir $CPlanExecutableFileName
$HandbookSourceDir = Resolve-RepoPath "handbook"
$PlanConfigPath = Join-Path $PackageDir "plan.config"
$PackageZipPath = Join-Path $OutDir "$PackageName-$PlatformName.zip"
$script:PackageLogPath = Join-Path $OutDir $PackageLogFileName

Assert-UnderRepo $OutDir
Assert-UnderRepo $PackageDir
Assert-UnderRepo $SourceDir
Assert-UnderRepo $EntryPoint
Assert-UnderRepo $HandbookSourceDir
Assert-UnderRepo $PlanConfigPath
Assert-UnderRepo $PackageZipPath

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Set-Content -LiteralPath $script:PackageLogPath -Value "" -Encoding UTF8
Write-PackageCheckpoint "START package RepoRoot=$RepoRoot Platform=$PlatformName"
if ($PythonPath) {
    $PythonCommand = if ([System.IO.Path]::IsPathFullyQualified($PythonPath)) {
        [System.IO.Path]::GetFullPath($PythonPath)
    }
    else {
        [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $PythonPath))
    }
    if (-not (Test-Path -LiteralPath $PythonCommand)) {
        $PythonCommand = [System.IO.Path]::GetFullPath($PythonPath)
    }
    if (-not (Test-Path -LiteralPath $PythonCommand)) {
        throw "指定的 PythonPath 不存在：$PythonPath"
    }
}
else {
    $pythonCommandInfo = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommandInfo) {
        throw "PATH 中没有找到 python。"
    }
    $PythonCommand = $pythonCommandInfo.Source
}
Write-PackageCheckpoint "Using Python: $PythonCommand"
if ($ProbeOnly) {
    Write-PackageCheckpoint ("Probe TEMP=" + [System.IO.Path]::GetTempPath())
    Write-PackageCheckpoint ("Probe PLAYWRIGHT_BROWSERS_PATH=" + [Environment]::GetEnvironmentVariable("PLAYWRIGHT_BROWSERS_PATH", "Process"))
    Write-PackageCheckpoint ("Probe PYINSTALLER_CONFIG_DIR=" + [Environment]::GetEnvironmentVariable("PYINSTALLER_CONFIG_DIR", "Process"))
    if (-not (Get-Command rg -ErrorAction SilentlyContinue)) {
        throw "分发版 AI 终端必须安装 ripgrep (rg)。请在 PowerShell 7 执行：winget install --id BurntSushi.ripgrep.MSVC -e"
    }
    Invoke-Checked $PythonCommand @(
        "-c",
        "import sys, pathlib, PyInstaller, textual, playwright; print('python', sys.executable); print('version', sys.version.split()[0]); print('pyinstaller', PyInstaller.__version__); print('textual', getattr(textual, '__version__', 'ok')); print('playwright', pathlib.Path(playwright.__file__).resolve())"
    )
    Write-PackageCheckpoint "Probe complete"
    return
}
if ($NoProcessCleanup) {
    Write-PackageCheckpoint "Skip existing package process cleanup"
}
else {
    Write-PackageCheckpoint "Stop existing package processes"
    Stop-ExistingPackageProcesses
}
Assert-UnderBuildTemp $BuildDir
Assert-UnderRepo $PackageDir
Assert-UnderRepo $PackageZipPath
Write-PackageCheckpoint "Remove build dir: $BuildDir"
Remove-PackagePath $BuildDir
Write-PackageCheckpoint "Remove package dir: $PackageDir"
Remove-PackagePath $PackageDir
Write-PackageCheckpoint "Remove package zip: $PackageZipPath"
Remove-PackagePath $PackageZipPath
New-Item -ItemType Directory -Force -Path $PackageDir | Out-Null
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
if ($StopAfter -eq "Cleanup") {
    Write-PackageCheckpoint "StopAfter Cleanup"
    return
}

if (-not (Get-Command rg -ErrorAction SilentlyContinue)) {
    throw "分发版 AI 终端必须安装 ripgrep (rg)。请在 PowerShell 7 执行：winget install --id BurntSushi.ripgrep.MSVC -e"
}

if ($InstallDependencies) {
    Invoke-Checked $PythonCommand @("-m", "pip", "install", "-e", ".[package]")
}

& $PythonCommand -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "未安装 PyInstaller。请执行：python -m pip install -e `".[package]`"，或用 -InstallDependencies 重新运行本脚本。"
}
& $PythonCommand -c "import textual" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "当前 Python 解释器缺少 textual。请执行：python -m pip install -e `".[package]`"，或用 -InstallDependencies 重新运行本脚本。"
}
$RequiredPackageModules = @("psycopg", "pymysql", "redis", "oracledb", "pyodbc", "pymongo")
$MissingPackageModules = @()
foreach ($moduleName in $RequiredPackageModules) {
    & $PythonCommand -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)" $moduleName 2>$null
    if ($LASTEXITCODE -ne 0) {
        $MissingPackageModules += $moduleName
    }
}
if ($MissingPackageModules.Count -gt 0) {
    throw "当前 Python 解释器缺少发行包数据库驱动：$($MissingPackageModules -join ', ')。请执行：python -m pip install -e `".[package]`"，或用 -InstallDependencies 重新运行本脚本。"
}
if ($StopAfter -eq "DependencyCheck") {
    Write-PackageCheckpoint "StopAfter DependencyCheck"
    return
}

$BrowserDir = (& $PythonCommand -c "from pathlib import Path; import playwright; print(Path(playwright.__file__).resolve().parent / 'driver' / 'package' / '.local-browsers')").Trim()
$BrowserBackupParent = $null
$BrowserBackupDir = $null
$previousBrowsersPath = [Environment]::GetEnvironmentVariable("PLAYWRIGHT_BROWSERS_PATH", "Process")
try {
    if ($BundleBrowser) {
        $env:PLAYWRIGHT_BROWSERS_PATH = "0"
        if ($SkipPlaywrightInstall) {
            Write-PackageCheckpoint "Skip Playwright Chromium install"
        }
        else {
            Write-PackageCheckpoint "Install Playwright Chromium for bundled package"
            Invoke-Checked $PythonCommand @("-m", "playwright", "install", "chromium")
        }
        if (-not (Test-Path -LiteralPath $BrowserDir)) {
            throw "没有找到 Playwright 浏览器目录：$BrowserDir"
        }
        Write-PackageCheckpoint "Playwright browser dir: $BrowserDir"
    }
    else {
        Write-PackageCheckpoint "Build lightweight package without bundled Playwright browsers"
    }
    if ($StopAfter -eq "PlaywrightInstall") {
        Write-PackageCheckpoint "StopAfter PlaywrightInstall"
        return
    }

    if (Test-Path -LiteralPath $BrowserDir) {
        $BrowserBackupParent = Join-Path ([System.IO.Path]::GetTempPath()) ("ai-automate-contro-playwright-browsers-{0}" -f [System.Guid]::NewGuid().ToString("N"))
        $BrowserBackupDir = Join-Path $BrowserBackupParent ".local-browsers"
        Write-PackageCheckpoint "Move Playwright browser cache away before PyInstaller: $BrowserBackupDir"
        New-Item -ItemType Directory -Force -Path $BrowserBackupParent | Out-Null
        Move-Item -LiteralPath $BrowserDir -Destination $BrowserBackupDir -Force
    }
    else {
        Write-PackageCheckpoint "No package-local Playwright browser cache before PyInstaller: $BrowserDir"
    }
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
        "--hidden-import", "ai_automate_contro.client.self_check",
        "--hidden-import", "ai_automate_contro.client.textual_app",
        "--hidden-import", "textual.app",
        "--hidden-import", "textual.containers",
        "--hidden-import", "textual.css.query",
        "--hidden-import", "textual.events",
        "--hidden-import", "textual.widgets"
    )
    $pyinstallerArgs += @($EntryPoint)
    try {
        Write-PackageCheckpoint "Run PyInstaller"
        Invoke-Checked $PythonCommand $pyinstallerArgs
    }
    finally {
        Write-PackageCheckpoint "Restore Playwright browser cache"
        if ($BrowserBackupDir -and (Test-Path -LiteralPath $BrowserBackupDir)) {
            if (Test-Path -LiteralPath $BrowserDir) {
                Remove-Item -LiteralPath $BrowserDir -Recurse -Force
            }
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $BrowserDir) | Out-Null
            Move-Item -LiteralPath $BrowserBackupDir -Destination $BrowserDir -Force
        }
        if ($BrowserBackupParent -and (Test-Path -LiteralPath $BrowserBackupParent)) {
            Remove-Item -LiteralPath $BrowserBackupParent -Recurse -Force
        }
    }
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
if ($StopAfter -eq "PyInstaller") {
    Write-PackageCheckpoint "StopAfter PyInstaller"
    return
}

Write-PackageCheckpoint "Copy PyInstaller output to package dir"
Remove-PackagePath $PackageDir
New-Item -ItemType Directory -Force -Path $PackageDir | Out-Null
Get-ChildItem -LiteralPath $PyInstallerPackageDir -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $PackageDir -Recurse -Force
}

if (-not (Test-Path -LiteralPath $ExecutablePath)) {
    throw "打包复制已完成，但没有找到可执行文件：$ExecutablePath"
}
Copy-Item -LiteralPath $ExecutablePath -Destination $CPlanExecutablePath -Force

$PackagedPlaywrightBrowserParent = Join-Path $PackageDir "_internal\playwright\driver\package"
$PackagedPlaywrightBrowserDir = Join-Path $PackagedPlaywrightBrowserParent ".local-browsers"
Assert-UnderRepo $PackagedPlaywrightBrowserDir
if (Test-Path -LiteralPath $PackagedPlaywrightBrowserDir) {
    Remove-PackagePath $PackagedPlaywrightBrowserDir
}
New-Item -ItemType Directory -Force -Path $PackagedPlaywrightBrowserParent | Out-Null
if ($BundleBrowser) {
    if (-not (Test-Path -LiteralPath $BrowserDir)) {
        throw "需要打包浏览器，但没有找到 Playwright 浏览器目录：$BrowserDir"
    }
    Write-PackageCheckpoint "Copy Playwright browsers into package"
    Copy-Item -LiteralPath $BrowserDir -Destination $PackagedPlaywrightBrowserDir -Recurse -Force
}
else {
    Write-PackageCheckpoint "Skip Playwright browsers copy for lightweight package"
}

if (-not $IsWindows) {
    chmod +x $ExecutablePath
    chmod +x $CPlanExecutablePath
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
    automation_type = "browser"
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
$CPlanExecutableCommandForDocs validate --file .\plans\demo\plan.json
$CPlanExecutableCommandForDocs run --file .\plans\demo\plan.json --run-name demo-smoke
```
"@
$demoReadme | Set-Content -LiteralPath (Join-Path $PackageDemoDocsDir "README.md") -Encoding UTF8
if ($StopAfter -eq "CopyPackage") {
    Write-PackageCheckpoint "StopAfter CopyPackage"
    return
}

if ($SmokeTest) {
    Push-Location $PackageDir
    try {
        if ($BundleBrowser) {
            Invoke-Checked $ExecutablePath @("self-check", "env")
        }
        else {
            Invoke-Checked $ExecutablePath @("install-browser", "--help")
            Invoke-Checked $CPlanExecutablePath @("install-browser", "--help")
        }
        Invoke-Checked $ExecutablePath @("self-check", "ai-stream")
        Invoke-Checked $ExecutablePath @("self-check", "textual-client")
        Invoke-Checked $ExecutablePath @("self-check", "ai-terminal")
        Invoke-Checked $ExecutablePath @("self-check", "ai-tools")
        Invoke-Checked $CPlanExecutablePath @("self-check", "cli")
        Invoke-Checked $CPlanExecutablePath @("self-check", "runtime")
        Invoke-Checked $ExecutablePath @("tool", "check")
        Invoke-Checked $CPlanExecutablePath @("validate", "--file", ".\plans\demo\plan.json")
        Invoke-Checked $CPlanExecutablePath @("run", "--file", ".\plans\demo\plan.json", "--run-name", "demo-smoke")
        if ($BundleBrowser) {
            Invoke-PackagedBrowserSmoke $CPlanExecutablePath
        }
        else {
            Write-PackageCheckpoint "Skip packaged browser smoke for lightweight package"
        }
    }
    finally {
        Pop-Location
    }
}

if (Test-Path -LiteralPath $PackageDemoOutputDir) {
    Assert-UnderRepo $PackageDemoOutputDir
    Remove-Item -LiteralPath $PackageDemoOutputDir -Recurse -Force
}

if (-not $SkipZip) {
    if (Test-Path -LiteralPath $PackageZipPath) {
        Remove-PackagePath $PackageZipPath
    }
    Write-PackageCheckpoint "Compress package zip"
    Compress-Archive -LiteralPath $PackageDir -DestinationPath $PackageZipPath -Force
}
else {
    Write-PackageCheckpoint "Skip package zip"
}

if ($SmokeTest -and -not $SkipZip) {
    $ZipSmokeDir = Join-Path $OutDir "zip-smoke"
    if (Test-Path -LiteralPath $ZipSmokeDir) {
        Remove-Item -LiteralPath $ZipSmokeDir -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $ZipSmokeDir | Out-Null
    Expand-Archive -LiteralPath $PackageZipPath -DestinationPath $ZipSmokeDir -Force
    $ExtractedPackageDir = Join-Path $ZipSmokeDir $PackageName
    $ExtractedExecutablePath = Join-Path $ExtractedPackageDir $ExecutableFileName
    $ExtractedCPlanExecutablePath = Join-Path $ExtractedPackageDir $CPlanExecutableFileName
    Push-Location $ExtractedPackageDir
    try {
        if ($BundleBrowser) {
            Invoke-Checked $ExtractedExecutablePath @("self-check", "env")
        }
        else {
            Invoke-Checked $ExtractedExecutablePath @("install-browser", "--help")
            Invoke-Checked $ExtractedCPlanExecutablePath @("install-browser", "--help")
        }
        Invoke-Checked $ExtractedExecutablePath @("self-check", "ai-stream")
        Invoke-Checked $ExtractedExecutablePath @("self-check", "textual-client")
        Invoke-Checked $ExtractedExecutablePath @("self-check", "ai-terminal")
        Invoke-Checked $ExtractedExecutablePath @("self-check", "ai-tools")
        Invoke-Checked $ExtractedCPlanExecutablePath @("self-check", "cli")
        Invoke-Checked $ExtractedCPlanExecutablePath @("self-check", "runtime")
        Invoke-Checked $ExtractedExecutablePath @("tool", "check")
        Invoke-Checked $ExtractedCPlanExecutablePath @("validate", "--file", ".\plans\demo\plan.json")
        Invoke-Checked $ExtractedCPlanExecutablePath @("run", "--file", ".\plans\demo\plan.json", "--run-name", "demo-smoke")
        if ($BundleBrowser) {
            Invoke-PackagedBrowserSmoke $ExtractedCPlanExecutablePath
        }
        else {
            Write-PackageCheckpoint "Skip zip browser smoke for lightweight package"
        }
    }
    finally {
        Pop-Location
        Remove-Item -LiteralPath $ZipSmokeDir -Recurse -Force
    }
}

if (Test-Path -LiteralPath $BuildDir) {
    Assert-UnderBuildTemp $BuildDir
    Remove-PackagePath $BuildDir
}
$BuildRoot = Split-Path -Parent $BuildDir
if ((Test-Path -LiteralPath $BuildRoot) -and -not (Get-ChildItem -LiteralPath $BuildRoot -Force)) {
    Assert-UnderBuildTemp $BuildRoot
    Remove-Item -LiteralPath $BuildRoot -Force
}

Write-Host "分发包可执行文件："
Write-Host $ExecutablePath
Write-Host "分发包 plan 控制 CLI："
Write-Host $CPlanExecutablePath
Write-Host "分发包 zip："
Write-Host $PackageZipPath
Write-Host "打包日志："
Write-Host $script:PackageLogPath
if ($BundleBrowser) {
    Write-Host "浏览器策略：已打包 Playwright Chromium。"
}
else {
    Write-Host "浏览器策略：轻量包未打包 Playwright 浏览器；首次运行浏览器 plan 前请在分发目录执行：.\aic.exe install-browser"
}
Write-Host "Python 依赖策略：不显式排除代码依赖；需要支持的 Python 能力必须先装进打包 Python 环境，不能依赖用户后续 pip 补进 _internal。"
Write-Host "数据库驱动策略：PostgreSQL、MySQL、Oracle、SQL Server、Redis、MongoDB 驱动由 .[package] 打包环境随包提供。"
Write-Host "请从 out\$PackageName 目录运行，或编辑 plan.config 指向其他 handbook/plans 位置。"
