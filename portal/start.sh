#!/usr/bin/env bash
# ============================================================================
#  网点决策台 · 一键启动本机服务（Git Bash / macOS / Linux）
#
#  做四件事：找 Python → 检查依赖 → 挑一个没被占用的端口 → 起服务并开浏览器
#  用法：  bash portal/start.sh
#          bash portal/start.sh --no-browser
#          bash portal/start.sh --port 9000
#  停止服务：Ctrl+C
# ============================================================================
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

# 统一 UTF-8：Windows 上 Python 在输出被重定向时默认用本地编码（GBK），
# 与 Bash 的 UTF-8 混在一起会让中文变成乱码。
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

echo
echo "============================================================================"
echo "  网点决策台 · 本地服务"
echo "============================================================================"

# ---------- 1/4 找 Python（优先仓库自带的虚拟环境） ----------
PY=""
for cand in \
  "datakit/.venv/Scripts/python.exe" \
  "datakit/.venv/bin/python" \
  ".venv/Scripts/python.exe" \
  ".venv/bin/python"; do
  if [ -x "$cand" ]; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
  done
fi
if [ -z "$PY" ]; then
  echo "  [x] 找不到 Python。"
  echo "      请安装 Python 3.11+，或恢复仓库自带的 datakit/.venv（见 datakit/README.md）。"
  exit 1
fi

# ---------- 2/4 检查依赖 ----------
if ! "$PY" -c "import datakit,pandas,numpy" 2>/dev/null; then
  echo "  [x] 依赖不可用：需要 datakit + pandas + numpy。"
  echo "      本产品应当用仓库自带的虚拟环境启动： datakit/.venv"
  echo "      若该环境缺失，请按 datakit/README.md 重建后再试。"
  exit 1
fi
echo "  Python   : $PY"
echo "  依赖     : $("$PY" -c 'import datakit,pandas;print("datakit "+datakit.__version__+" | pandas "+pandas.__version__)')"
if "$PY" -c "import statsmodels,libpysal,esda,spreg" 2>/dev/null; then
  echo "  可选依赖 : 齐全（数据接入 + 现场重估 + 空间口径全部可用）"
else
  echo "  可选依赖 : 缺少 statsmodels / libpysal / esda / spreg"
  echo "             → 「用数据重估系数」与「空间口径」会降级，其余功能正常"
fi

# ---------- 3/4 挑一个空闲端口（用户显式传了 --port 就不管） ----------
PORTARG=0
for a in "$@"; do [ "$a" = "--port" ] && PORTARG=1; done
PORT=""
if [ "$PORTARG" = "0" ]; then
  for p in 8765 8766 8767 8768 8770 8771 8772 8773; do
    if "$PY" -c "
import socket, sys
s = socket.socket()
try:
    s.bind(('127.0.0.1', int(sys.argv[1])))
except OSError:
    sys.exit(1)
finally:
    s.close()
" "$p" 2>/dev/null; then PORT="$p"; break; fi
  done
  [ -z "$PORT" ] && PORT=8799
  echo "  端口     : $PORT   (8765 起第一个空闲端口)"
else
  echo "  端口     : 由参数指定"
fi

# ---------- 4/4 启动 ----------
echo
echo "  浏览器会自动打开产品页；按 Ctrl+C 即停止服务。"
echo "----------------------------------------------------------------------------"
echo

if [ "$PORTARG" = "1" ]; then
  exec "$PY" portal/serve.py "$@"
else
  exec "$PY" portal/serve.py --port "$PORT" "$@"
fi
