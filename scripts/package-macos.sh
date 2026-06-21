#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./scripts/package-macos.sh [--install-dependencies] [--clean] [--smoke-test]

Options:
  --install-dependencies  Install editable project dependencies with package extras.
  --clean                 Accepted for compatibility; package output is always removed before building.
  --smoke-test            Run packaged executable self-checks and a browser smoke plan.
  --python PATH           Use a specific Python interpreter.
  -h, --help              Show this help.

Environment:
  PYTHON                  Python interpreter path, same as --python.
  PIP_REQUIRE_VIRTUALENV  Set to false if local pip config requires a virtualenv.
  PIP_BREAK_SYSTEM_PACKAGES
                          Set to 1 for Homebrew Python user/global maintenance when pip enforces PEP 668.
EOF
}

die() {
  printf '错误：%s\n' "$*" >&2
  exit 1
}

run_checked() {
  "$@"
}

run_packaged_browser_smoke() {
  local cplan_path="$1"
  local browser_smoke_dir
  browser_smoke_dir="$(mktemp -d "${TMPDIR:-/tmp}/ai-automate-browser-smoke.XXXXXX")"
  mkdir -p "$browser_smoke_dir/resources"
  cat > "$browser_smoke_dir/resources/demo.html" <<'HTML'
<!doctype html>
<html>
  <head><meta charset="utf-8"><title>Packaged Browser Smoke</title></head>
  <body><h1 id="title">Packaged Browser Smoke</h1></body>
</html>
HTML
  cat > "$browser_smoke_dir/plan.json" <<'JSON'
{
  "name": "packaged-browser-smoke",
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
JSON
  run_checked "$cplan_path" validate --file "$browser_smoke_dir/plan.json"
  run_checked "$cplan_path" run --file "$browser_smoke_dir/plan.json" --run-name "browser-smoke"
  rm -rf "$browser_smoke_dir"
}

real_path() {
  "$python_bin" - "$1" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).expanduser().resolve(strict=False))
PY
}

assert_path_under() {
  local target_path="$1"
  local allowed_root="$2"
  local resolved_target
  local resolved_root
  resolved_target="$(real_path "$target_path")"
  resolved_root="$(real_path "$allowed_root")"
  case "$resolved_target" in
    "$resolved_root"|"$resolved_root"/*)
      ;;
    *)
      die "拒绝操作允许目录外路径：$resolved_target"
      ;;
  esac
}

stop_existing_package_processes() {
  "$python_bin" - "$repo_root" "$package_dir" "$executable_path" "$build_temp_root" "$executable_name" <<'PY'
import os
import signal
import subprocess
import sys
import time

repo_root = os.path.realpath(sys.argv[1])
package_dir = os.path.realpath(sys.argv[2])
executable_path = os.path.realpath(sys.argv[3])
build_temp_root = os.path.realpath(sys.argv[4])
executable_name = sys.argv[5]
executable_names = {executable_name, "cplan"}


def ancestor_pids(pid: int) -> set[int]:
    result = {pid}
    while pid > 1:
        try:
            output = subprocess.check_output(["ps", "-o", "ppid=", "-p", str(pid)], text=True).strip()
            parent = int(output or "0")
        except Exception:
            break
        if parent <= 1 or parent in result:
            break
        result.add(parent)
        pid = parent
    return result


def process_cwd(pid: int) -> str:
    try:
        output = subprocess.check_output(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"], text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return ""
    for line in output.splitlines():
        if line.startswith("n"):
            return os.path.realpath(line[1:])
    return ""


current_tree = ancestor_pids(os.getpid())
try:
    rows = subprocess.check_output(["ps", "-axo", "pid=,comm=,command="], text=True)
except Exception:
    rows = ""

pids: list[int] = []
for row in rows.splitlines():
    parts = row.strip().split(None, 2)
    if len(parts) < 2:
        continue
    try:
        pid = int(parts[0])
    except ValueError:
        continue
    if pid in current_tree:
        continue
    comm = os.path.basename(parts[1])
    command = parts[2] if len(parts) >= 3 else ""
    cwd = process_cwd(pid)
    runs_from_package_dir = bool(cwd and (cwd == package_dir or cwd.startswith(f"{package_dir}/")))
    matches_packaged_process = (
        executable_path in command
        or f"{package_dir}/" in command
        or (runs_from_package_dir and comm in executable_names)
        or (
            runs_from_package_dir
            and any(command.startswith(f"./{name} ") or command == f"./{name}" for name in executable_names)
        )
    )
    matches_stale_packager = (
        ("package-macos.sh" in command and repo_root in command)
        or ("PyInstaller" in command and build_temp_root in command)
        or (repo_root in command and build_temp_root in command)
    )
    if matches_packaged_process or matches_stale_packager:
        pids.append(pid)

if not pids:
    raise SystemExit(0)

print("停止旧打包/分发包进程：" + ", ".join(str(pid) for pid in sorted(set(pids))))
for pid in sorted(set(pids)):
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
time.sleep(1.0)
for pid in sorted(set(pids)):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        continue
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
PY
}

remove_existing_path() {
  local target_path="$1"
  local allowed_root="$2"
  assert_path_under "$target_path" "$allowed_root"
  [ -e "$target_path" ] || [ -L "$target_path" ] || return 0
  if rm -rf "$target_path"; then
    return 0
  fi
  stop_existing_package_processes
  sleep 1
  rm -rf "$target_path"
}

install_dependencies=0
clean=0
smoke_test=0
python_bin="${PYTHON:-}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --install-dependencies)
      install_dependencies=1
      ;;
    --clean)
      clean=1
      ;;
    --smoke-test)
      smoke_test=1
      ;;
    --python)
      shift
      [ "$#" -gt 0 ] || die "--python 需要一个路径。"
      python_bin="$1"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "未知参数：$1"
      ;;
  esac
  shift
done

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
cd "$repo_root"

[ "$(uname -s)" = "Darwin" ] || die "当前脚本只支持 macOS。"
[ "$(uname -m)" = "arm64" ] || die "macOS 打包目前只支持 Apple Silicon arm64，当前架构：$(uname -m)"

if [ -z "$python_bin" ]; then
  if command -v python >/dev/null 2>&1; then
    python_bin="$(command -v python)"
  elif command -v python3 >/dev/null 2>&1; then
    python_bin="$(command -v python3)"
  else
    die "PATH 中没有找到 python 或 python3。"
  fi
fi

[ -x "$python_bin" ] || die "Python 不可执行：$python_bin"

run_checked "$python_bin" - <<'PY'
import sys

if sys.version_info < (3, 11):
    raise SystemExit(f"需要 Python 3.11 或更高版本，当前是 {sys.version.split()[0]}")
PY

platform_name="macos-arm64"
executable_name="aic"
cplan_executable_name="cplan"

command -v rg >/dev/null 2>&1 || die "分发版 AI 终端依赖 ripgrep (rg)。macOS 可先执行：brew install ripgrep"

if [ "$install_dependencies" -eq 1 ]; then
  if ! "$python_bin" -m pip install -e ".[package]"; then
    die "依赖安装失败。项目默认不创建 .venv；如果当前 Python 的 pip 被本机策略拦截，可先设置 PIP_REQUIRE_VIRTUALENV=false，Homebrew Python 还可能需要 PIP_BREAK_SYSTEM_PACKAGES=1，或用 --python 指向你准备好的解释器。"
  fi
fi

run_checked "$python_bin" - <<'PY'
from importlib.util import find_spec

missing = []
for name in ("PyInstaller", "textual"):
    spec = find_spec(name)
    if spec is None:
        missing.append(name)
        continue
    if name == "textual" and not spec.submodule_search_locations:
        missing.append(name)
if missing:
    raise SystemExit(
        "当前 Python 解释器缺少打包依赖："
        + ", ".join(missing)
        + "。请执行：./scripts/package-macos.sh --install-dependencies --clean --smoke-test，"
        + "或用 --python 指向已安装项目依赖的解释器。"
    )
PY

run_checked env PLAYWRIGHT_BROWSERS_PATH=0 "$python_bin" -m playwright install chromium

out_dir="$repo_root/out"
package_dir="$out_dir/ai-automate-contro"
zip_path="$out_dir/ai-automate-contro-$platform_name.zip"
build_temp_root="${TMPDIR:-/tmp}/ai-automate-contro-pyinstaller"
build_dir="$build_temp_root/$platform_name"
pyinstaller_dist_dir="$build_dir/dist"
pyinstaller_config_dir="$build_dir/pyinstaller-config"
source_dir="$repo_root/src"
entry_point="$repo_root/main.py"
executable_path="$package_dir/$executable_name"
cplan_executable_path="$package_dir/$cplan_executable_name"
package_plans_config_path="$package_dir/plans/config.json"

mkdir -p "$out_dir"

stop_existing_package_processes
remove_existing_path "$build_dir" "$build_temp_root"
remove_existing_path "$package_dir" "$out_dir"
remove_existing_path "$zip_path" "$out_dir"
mkdir -p "$build_dir" "$package_dir"

browser_dir="$("$python_bin" - <<'PY'
from pathlib import Path
import playwright

print(Path(playwright.__file__).resolve().parent / "driver" / "package" / ".local-browsers")
PY
)"
[ -d "$browser_dir" ] || die "没有找到 Playwright 浏览器目录：$browser_dir"

browser_backup_parent="$(mktemp -d "${TMPDIR:-/tmp}/ai-automate-contro-playwright-browsers.XXXXXX")"
browser_backup="$browser_backup_parent/.local-browsers"

restore_browsers() {
  if [ -d "$browser_backup" ]; then
    rm -rf "$browser_dir"
    mkdir -p "$(dirname "$browser_dir")"
    mv "$browser_backup" "$browser_dir"
  fi
  rm -rf "$browser_backup_parent"
}

trap restore_browsers EXIT
mv "$browser_dir" "$browser_backup"

env PYINSTALLER_CONFIG_DIR="$pyinstaller_config_dir" "$python_bin" -m PyInstaller \
  --noconfirm \
  --clean \
  --onedir \
  --console \
  --noupx \
  --contents-directory "_internal" \
  --name "$executable_name" \
  --distpath "$pyinstaller_dist_dir" \
  --workpath "$build_dir" \
  --specpath "$build_dir" \
  --paths "$source_dir" \
  --collect-data "playwright" \
  --collect-data "textual" \
  --collect-submodules "langchain" \
  --collect-submodules "langchain_openai" \
  --collect-submodules "langgraph" \
  --collect-submodules "langgraph.checkpoint.sqlite" \
  --collect-submodules "rich" \
  --collect-submodules "textual" \
  --hidden-import "ai_automate_contro.client.self_check" \
  --hidden-import "ai_automate_contro.client.textual_app" \
  --hidden-import "textual.app" \
  --hidden-import "textual.containers" \
  --hidden-import "textual.css.query" \
  --hidden-import "textual.events" \
  --hidden-import "textual.widgets" \
  "$entry_point"

restore_browsers
trap - EXIT

pyinstaller_package_dir="$pyinstaller_dist_dir/$executable_name"
[ -d "$pyinstaller_package_dir" ] || die "打包已完成，但没有找到 PyInstaller 输出目录：$pyinstaller_package_dir"

remove_existing_path "$package_dir" "$out_dir"
mkdir -p "$package_dir"
cp -R "$pyinstaller_package_dir/." "$package_dir/"
[ -f "$executable_path" ] || die "打包复制已完成，但没有找到可执行文件：$executable_path"
chmod +x "$executable_path"
cp "$executable_path" "$cplan_executable_path"
chmod +x "$cplan_executable_path"

mkdir -p "$package_dir/_internal/playwright/driver/package"
cp -R "$browser_dir" "$package_dir/_internal/playwright/driver/package/.local-browsers"

rm -rf "$package_dir/handbook"
cp -R "$repo_root/handbook" "$package_dir/handbook"

mkdir -p "$package_dir/plans/demo/docs"

cat > "$package_dir/plan.config" <<'JSON'
{
  "handbook_path": "handbook",
  "plan_roots": [
    "plans"
  ],
  "default_ai_config_dir": "plans"
}
JSON

cat > "$package_plans_config_path" <<'JSON'
{
  "description": "分发包 plans 的共享配置。需要使用 AI 终端或 ai action 时，请在这里添加 ai_services.default。"
}
JSON

cat > "$package_dir/plans/demo/plan.json" <<'JSON'
{
  "name": "packaged-demo",
  "variables": {},
  "steps": [
    {
      "action": "print",
      "message": "分发包 demo plan 可用。"
    }
  ]
}
JSON

cat > "$package_dir/plans/demo/docs/README.md" <<EOF
# 分发包 demo

这个 plan 用于验证分发包是否可以正常校验和运行。

\`\`\`bash
./$cplan_executable_name validate --file ./plans/demo/plan.json
./$cplan_executable_name run --file ./plans/demo/plan.json --run-name demo-smoke
\`\`\`
EOF

if [ "$smoke_test" -eq 1 ]; then
  (
    cd "$package_dir"
    run_checked "./$executable_name" self-check env
    run_checked "./$executable_name" self-check ai-stream
    run_checked "./$executable_name" self-check textual-client
    run_checked "./$executable_name" self-check ai-terminal
    run_checked "./$cplan_executable_name" self-check cli
    run_checked "./$cplan_executable_name" self-check runtime
    run_checked "./$executable_name" tool check
    run_checked "./$executable_name" self-check ai-tools
    run_checked "./$cplan_executable_name" validate --file "./plans/demo/plan.json"
    run_checked "./$cplan_executable_name" run --file "./plans/demo/plan.json" --run-name "demo-smoke"
  )

  run_packaged_browser_smoke "$cplan_executable_path"
  rm -rf "$package_dir/plans/demo/output"
fi

(
  cd "$out_dir"
  zip -qr "$(basename "$zip_path")" "$(basename "$package_dir")"
)

if [ "$smoke_test" -eq 1 ]; then
  zip_smoke_dir="$(mktemp -d "${TMPDIR:-/tmp}/ai-automate-zip-smoke.XXXXXX")"
  unzip -q "$zip_path" -d "$zip_smoke_dir"
  (
    cd "$zip_smoke_dir/ai-automate-contro"
    run_checked "./$executable_name" self-check env
    run_checked "./$executable_name" self-check ai-stream
    run_checked "./$cplan_executable_name" self-check cli
    run_checked "./$cplan_executable_name" self-check runtime
    run_checked "./$executable_name" self-check textual-client
    run_checked "./$executable_name" self-check ai-terminal
    run_checked "./$executable_name" self-check ai-tools
    run_checked "./$executable_name" tool check
    run_checked "./$cplan_executable_name" validate --file "./plans/demo/plan.json"
    run_checked "./$cplan_executable_name" run --file "./plans/demo/plan.json" --run-name "zip-demo-smoke"
    run_packaged_browser_smoke "./$cplan_executable_name"
  )
  rm -rf "$zip_smoke_dir"
fi

remove_existing_path "$build_dir" "$build_temp_root"
if [ -d "$build_temp_root" ] && [ -z "$(find "$build_temp_root" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
  rmdir "$build_temp_root"
fi

printf '分发包可执行文件：\n%s\n' "$executable_path"
printf '分发包 plan 控制 CLI：\n%s\n' "$cplan_executable_path"
printf '分发包 zip：\n%s\n' "$zip_path"
printf '请从 out/ai-automate-contro 目录运行，或编辑 plan.config 指向其他 handbook/plans 位置。\n'
