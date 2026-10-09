#!/usr/bin/env bash
# =============================================================================
# FillinForm - macOS / Linux Launcher
# =============================================================================

# 切換至腳本所在目錄
cd "$(cd "$(dirname "$0")" && pwd)"

echo "========================================================================="
echo "  FillinForm - NTUST Peer Review Synchronizer (macOS/Linux)"
echo "========================================================================="
echo ""

PYTHON_CMD=""

# 1. 優先檢測既有虛擬環境 (macOS/Linux 的路徑為 bin/python)
if [ -f "../../.venv/bin/python" ]; then
    PYTHON_CMD="../../.venv/bin/python"
elif [ -f "../.venv/bin/python" ]; then
    PYTHON_CMD="../.venv/bin/python"
elif [ -f ".venv/bin/python" ]; then
    PYTHON_CMD=".venv/bin/python"
fi

# 2. 若無現成 .venv，檢測系統 python3 並自動建立虛擬環境
if [ -z "$PYTHON_CMD" ]; then
    SYS_PYTHON=""
    if command -v python3 >/dev/null 2>&1; then
        SYS_PYTHON="python3"
    elif command -v python >/dev/null 2>&1; then
        SYS_PYTHON="python"
    else
        echo "[錯誤] 找不到 Python！請確認您的 Mac 是否已安裝 Python 3.10+。"
        echo "提示：可至 https://www.python.org 下載安裝，或使用 'brew install python'。"
        read -p "請按 Enter 鍵離開..."
        exit 1
    fi

    echo "[設定] 首次在 Mac 執行，正在建立專屬 .venv 虛擬環境..."
    "$SYS_PYTHON" -m venv .venv
    if [ $? -ne 0 ]; then
        echo "[錯誤] 虛擬環境建立失敗！"
        read -p "請按 Enter 鍵離開..."
        exit 1
    fi

    PYTHON_CMD=".venv/bin/python"
fi

# 3. 檢查套件完整性
echo "[1/2] 正在檢查執行環境與相依套件..."
"$PYTHON_CMD" -c "import fastapi, uvicorn, requests, playwright" >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "[設定] 偵測到缺少相依套件，正在自動安裝中..."
    "$PYTHON_CMD" -m pip install --upgrade pip
    "$PYTHON_CMD" -m pip install -r requirements.txt
fi

echo "[2/2] 正在啟動 FillinForm 核心啟動器..."
"$PYTHON_CMD" --version
echo "儀表板網址: http://127.0.0.1:8000"
echo ""

# 啟動守護啟動器 (啟動器內部會自動檢查更新並啟動伺服器)
"$PYTHON_CMD" launcher.py
