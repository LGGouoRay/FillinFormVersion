"""
FillinForm - Application Supervisor & Launcher (launcher.py)
核心啟動器守護程序：
1. 啟動前進行 GitHub Releases 版本檢查與終端互動選單
2. 啟動並監控 server.py 子程序
3. 監聽網頁端發起之一鍵更新信號 (Exit Code 42 / .update_requested)
4. 於 server.py 完全釋放資源後執行獨立安裝與無縫重啟
"""

import os
import sys
import time
import json
import subprocess
from typing import Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from core.version import APP_VERSION, APP_TITLE, GITHUB_OWNER, GITHUB_REPO
from core.updater import check_github_latest, perform_full_update


def clear_update_flags():
    """清理殘留的更新標記檔案"""
    flag = os.path.join(BASE_DIR, ".update_requested")
    if os.path.exists(flag):
        try:
            os.remove(flag)
        except Exception:
            pass


def print_banner(version: str):
    print("=" * 70)
    print(f"  {APP_TITLE} — 核心啟動器 (v{version})")
    print("=" * 70, flush=True)


def check_and_prompt_startup_update() -> bool:
    """
    雙擊啟動時執行版本檢查。
    若發現新版本，強制停在選單由使用者在終端機選擇是否更新。
    回傳 True 表示已執行更新（將重載最新版本設定），False 表示繼續執行目前版本。
    """
    print("\n🔍 正在連線檢查是否有新版本 (逾時上限 4 秒)...", flush=True)
    info = check_github_latest(owner=GITHUB_OWNER, repo=GITHUB_REPO, timeout=4)

    if info.get("error"):
        print(f"ℹ️ 連線檢查提示：{info['error']}")
        print(f"🚀 將直接使用本機目前版本 (v{APP_VERSION}) 啟動！\n", flush=True)
        return False

    if not info.get("has_update"):
        print(f"✅ 目前已是最新版本 (v{APP_VERSION})，無須更新。\n", flush=True)
        return False

    latest_ver = info.get("latest_version")
    curr_ver = info.get("current_version")
    notes = info.get("release_notes", "").strip()
    download_url = info.get("download_url")

    print("\n" + "=" * 70)
    print(f"  🔔 發現新版本可用！")
    print(f"  目前版本：v{curr_ver}  ➔  最新版本：v{latest_ver}")
    print("=" * 70)
    if notes:
        print("【更新內容摘要】")
        for line in notes.split("\n")[:6]:
            print(f"  • {line.strip()}")
        print("-" * 70)
    print("  [1] 立即更新並啟動新版 (自動下載與安裝)")
    print(f"  [2] 稍後更新，繼續使用目前版本 (v{curr_ver})")
    print("=" * 70, flush=True)

    while True:
        try:
            choice = input("請輸入選項 [1/2] (直接按 Enter 預設為 1): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n略過更新，使用目前版本啟動。")
            return False

        if not choice or choice == "1":
            print(f"\n⏳ 正在為您自動下載並安裝新版本 (v{latest_ver})...", flush=True)
            res = perform_full_update(
                download_url=download_url,
                target_dir=BASE_DIR,
                progress_callback=lambda msg: print(f"  [進度] {msg}", flush=True)
            )
            if res.get("success"):
                print(f"🎉 成功更新至 v{latest_ver}！正在為您啟動新版程式...\n", flush=True)
                return True
            else:
                print(f"\n⚠️ 更新失敗：{res.get('error')}")
                print(f"🛡️ 系統已自動還原至目前穩定版本 (v{curr_ver})。")
                try:
                    input("請按 Enter 鍵繼續以目前版本啟動...")
                except Exception:
                    pass
                return False

        elif choice == "2":
            print(f"\n⏩ 已略過更新，正在以目前版本 (v{curr_ver}) 啟動...\n", flush=True)
            return False
        else:
            print("無效輸入，請輸入 1 或 2！")


def run_supervised_server():
    """
    常駐監控主伺服器行程：
    當使用者在網頁介面點擊「更新並重新啟動」時，
    server.py 會安全關閉瀏覽器與資源並發送 Exit Code 42 (或寫入 .update_requested)，
    launcher.py 確認伺服器徹底退出後，執行熱更新並重啟 server.py！
    """
    clear_update_flags()

    # 1. 雙擊啟動時的版本檢查與終端選單互動
    check_and_prompt_startup_update()

    # 2. 啟動伺服器並進入守護監控迴圈
    is_restarted = False
    while True:
        # 動態載入目前版本號 (確保更新後顯示最新版)
        try:
            import importlib
            import core.version
            importlib.reload(core.version)
            active_version = core.version.APP_VERSION
        except Exception:
            active_version = APP_VERSION

        print(f"🚀 正在啟動 FillinForm 伺服器 (v{active_version})...", flush=True)
        sub_env = os.environ.copy()
        if is_restarted:
            sub_env["LAUNCHER_RESTARTED"] = "1"
        server_proc = subprocess.Popen([sys.executable, "server.py"], cwd=BASE_DIR, env=sub_env)

        # 監控直到伺服器行程結束
        while True:
            ret = server_proc.poll()
            if ret is not None:
                break
            time.sleep(0.5)

        # 行程已完全退出，檢查是否為「網頁發動之一鍵更新」
        update_flag = os.path.join(BASE_DIR, ".update_requested")
        is_update_request = (ret == 42) or os.path.exists(update_flag)

        if is_update_request:
            print("\n" + "=" * 70, flush=True)
            print("🔄 收到網頁端發動之一鍵更新請求！", flush=True)
            print("正在確認後端與瀏覽器資源徹底釋放...", flush=True)
            time.sleep(1.0)

            download_url = None
            target_version = None
            if os.path.exists(update_flag):
                try:
                    with open(update_flag, "r", encoding="utf-8") as f:
                        flag_data = json.load(f)
                        download_url = flag_data.get("download_url")
                        target_version = flag_data.get("target_version")
                except Exception as e:
                    print(f"⚠️ 讀取更新標記失敗: {e}")
                clear_update_flags()

            if not download_url:
                print("🔍 正在查詢最新版本發布直鏈...", flush=True)
                latest_info = check_github_latest(owner=GITHUB_OWNER, repo=GITHUB_REPO, timeout=6)
                download_url = latest_info.get("download_url")
                target_version = latest_info.get("latest_version")

            if download_url:
                print(f"⏳ 正在下載最新版本 (目標版本: v{target_version or '最新'})...", flush=True)
                res = perform_full_update(
                    download_url=download_url,
                    target_dir=BASE_DIR,
                    progress_callback=lambda msg: print(f"  [熱更新] {msg}", flush=True)
                )
                if res.get("success"):
                    print("🎉 熱更新套用成功！正在自動重新啟動伺服器...", flush=True)
                else:
                    print(f"⚠️ 熱更新失敗：{res.get('error')}，已自動還原舊版本並重啟！", flush=True)
            else:
                print("⚠️ 無法獲取更新檔案下載連結，將重新啟動目前版本！", flush=True)

            print("=" * 70 + "\n", flush=True)
            time.sleep(1.0)
            is_restarted = True
            # 繼續 while True 重新啟動伺服器
            continue
        else:
            # 正常關閉或 Ctrl+C 結束
            print(f"👋 FillinForm 伺服器已退出 (Code: {ret})。再見！", flush=True)
            sys.exit(ret)


if __name__ == "__main__":
    print_banner(APP_VERSION)
    try:
        run_supervised_server()
    except KeyboardInterrupt:
        print("\n使用者中斷，啟動器已結束。")
        sys.exit(0)
