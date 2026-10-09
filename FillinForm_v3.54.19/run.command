#!/usr/bin/env bash
# =============================================================================
# FillinForm - macOS Finder Double-Click Launcher
# 雙擊此檔案即可直接在 Mac 上啟動 FillinForm
# =============================================================================

# 切換至腳本所在目錄
cd "$(cd "$(dirname "$0")" && pwd)"

# 賦予 run.sh 執行權限並執行
chmod +x ./run.sh 2>/dev/null
./run.sh
