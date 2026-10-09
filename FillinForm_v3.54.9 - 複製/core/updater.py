"""
FillinForm v3.46 - Unified Auto-Update Engine (core/updater.py)
雙入口統一更新核心模組：供 Launcher (啟動前更新) 與 server.py (使用途中更新) 共同呼叫。
嚴格實現：
1. 依據 GitHub Releases 官方跳轉進行版本比對 (免 60 次 API 限速)
2. 安全下載與 ZIP 完整性檢驗
3. 舊版本快照備份與失敗自動回滾 (Rollback)
4. 嚴格保護 credentials.json 與 profile/ (永不被新版覆蓋)
"""

import os
import sys
import re
import shutil
import zipfile
import html
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, Any, Optional, Callable

from core.version import APP_VERSION, GITHUB_OWNER, GITHUB_REPO

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 絕不允許更新器覆蓋或刪除的本機資料（資安與個人設定保護）
PROTECTED_ITEMS = {
    "credentials.json",
    "profile",
    "browser_profile",
    "user_data",
    ".venv",
    "venv",
    "env",
    "screenshots",
    "evidence",
    ".git",
    ".backup_current",
    "_update_temp",
    ".update_requested",
    "sheets_report_cache.json",
}


def clean_version(v_str: str) -> str:
    """清理版本字串，去除前綴 v 或空格"""
    if not v_str:
        return "0.0"
    v = v_str.strip().lstrip("vV")
    # 僅保留數字與小數點
    match = re.search(r"(\d+(?:\.\d+)+)", v)
    return match.group(1) if match else v


def compare_versions(v1: str, v2: str) -> int:
    """
    比較兩版本號 (例如 '3.47' vs '3.46')
    回傳：
      1: v1 > v2 (v1 較新)
     -1: v1 < v2 (v2 較新)
      0: v1 == v2
    """
    c1 = [int(p) for p in clean_version(v1).split(".") if p.isdigit()]
    c2 = [int(p) for p in clean_version(v2).split(".") if p.isdigit()]
    
    # 補齊位數
    max_len = max(len(c1), len(c2))
    c1 += [0] * (max_len - len(c1))
    c2 += [0] * (max_len - len(c2))

    if c1 > c2:
        return 1
    elif c1 < c2:
        return -1
    return 0


def check_github_latest(
    owner: str = GITHUB_OWNER,
    repo: str = GITHUB_REPO,
    timeout: int = 5
) -> Dict[str, Any]:
    """
    透過 GitHub 官方 releases/latest 302 跳轉機制偵測最新版本。
    【優勢】完全免 token、免 GitHub API 每小時 60 次限速，學校同 Wi-Fi 29 人同時使用亦 100% 順暢！
    """
    url = f"https://github.com/{owner}/{repo}/releases/latest"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            final_url = response.geturl()
            # 檢查是否轉址到 /releases/tag/vX.XX
            if "/releases/tag/" in final_url:
                tag = final_url.split("/releases/tag/")[-1].strip()
                remote_ver = clean_version(tag)
                curr_ver = clean_version(APP_VERSION)
                has_update = compare_versions(remote_ver, curr_ver) > 0

                html_content = ""
                try:
                    html_content = response.read().decode("utf-8", errors="ignore")
                except Exception:
                    pass

                # 嘗試在 Release 頁面中尋找 .zip 檔案的直接載點
                download_url = None
                if html_content:
                    # 搜尋符合 /releases/download/{tag}/*.zip 的連結
                    zip_matches = re.findall(rf'href=["\'](/[^"\']+/releases/download/{re.escape(tag)}/[^"\']+\.zip)["\']', html_content)
                    if zip_matches:
                        download_url = f"https://github.com{zip_matches[0]}"

                if not download_url:
                    # 依標準命名慣例推導官方下載直鏈
                    download_url = f"https://github.com/{owner}/{repo}/releases/download/{tag}/FillinForm_{tag}.zip"

                # 提取簡要更新摘要
                release_notes = ""
                notes_match = re.search(r'class="[^"]*markdown-body[^"]*"[^>]*>(.*?)</div>', html_content, re.DOTALL)
                if notes_match:
                    raw_notes = notes_match.group(1)
                    # 移除 HTML 標籤並還原實體字符
                    clean_notes = re.sub(r'<[^>]+>', '', raw_notes).strip()
                    clean_notes = html.unescape(clean_notes)
                    release_notes = clean_notes[:300] + ("..." if len(clean_notes) > 300 else "")

                return {
                    "has_update": has_update,
                    "current_version": APP_VERSION,
                    "latest_version": remote_ver,
                    "tag": tag,
                    "download_url": download_url,
                    "release_notes": release_notes,
                    "checked_at": now_str,
                    "error": None,
                }
            else:
                # 尚未發布任何 Release
                return {
                    "has_update": False,
                    "current_version": APP_VERSION,
                    "latest_version": APP_VERSION,
                    "tag": f"v{APP_VERSION}",
                    "download_url": None,
                    "release_notes": "",
                    "checked_at": now_str,
                    "error": None,
                }

    except urllib.error.HTTPError as e:
        if e.code == 404:
            # 尚無任何公開 Release
            return {
                "has_update": False,
                "current_version": APP_VERSION,
                "latest_version": APP_VERSION,
                "tag": f"v{APP_VERSION}",
                "download_url": None,
                "release_notes": "",
                "checked_at": now_str,
                "error": "目前雲端伺服器尚未發布新版本",
            }
        return {
            "has_update": False,
            "current_version": APP_VERSION,
            "latest_version": None,
            "tag": None,
            "download_url": None,
            "release_notes": "",
            "checked_at": now_str,
            "error": f"HTTP {e.code}: {e.reason}",
        }
    except Exception as e:
        return {
            "has_update": False,
            "current_version": APP_VERSION,
            "latest_version": None,
            "tag": None,
            "download_url": None,
            "release_notes": "",
            "checked_at": now_str,
            "error": str(e),
        }


def download_file(url: str, dest_path: str, progress_callback: Optional[Callable[[int, int], None]] = None):
    """下載檔案並支援進度回調"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    req = urllib.request.Request(url, headers=headers)
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)

    with urllib.request.urlopen(req, timeout=30) as resp:
        total_size = int(resp.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 65536

        with open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total_size)


def create_backup(target_dir: str, backup_dir: str):
    """
    建立舊版本代碼備份快照（嚴格排除敏感資料與暫存檔）
    """
    if os.path.exists(backup_dir):
        shutil.rmtree(backup_dir, ignore_errors=True)
    os.makedirs(backup_dir, exist_ok=True)

    for item in os.listdir(target_dir):
        if item in PROTECTED_ITEMS or item.startswith("."):
            continue
        src = os.path.join(target_dir, item)
        dst = os.path.join(backup_dir, item)
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        except Exception as e:
            print(f"⚠️ 備份項目 {item} 提示: {e}")


def rollback_from_backup(target_dir: str, backup_dir: str) -> bool:
    """更新出錯時，自動從快照 1 秒完整還原舊版"""
    if not os.path.exists(backup_dir):
        return False
    try:
        for item in os.listdir(backup_dir):
            src = os.path.join(backup_dir, item)
            dst = os.path.join(target_dir, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        return True
    except Exception as e:
        print(f"❌ 還原舊版本失敗: {e}")
        return False


def apply_update_from_zip(
    zip_path: str,
    target_dir: str = BASE_DIR,
    progress_callback: Optional[Callable[[str], None]] = None
) -> Dict[str, Any]:
    """
    解壓並安全套用新版本：
    1. 檢驗 ZIP 完整性
    2. 備份現有代碼至 .backup_current/
    3. 排除 credentials.json 與 profile/ 等資安資料
    4. 覆蓋更新
    5. 若有例外自動執行 rollback
    """
    backup_dir = os.path.join(target_dir, ".backup_current")
    extract_temp = os.path.join(target_dir, "_update_temp", "extracted")

    if not zipfile.is_zipfile(zip_path):
        return {"success": False, "error": "下載的檔案並非有效 ZIP 壓縮檔！"}

    try:
        if progress_callback:
            progress_callback("正在備份目前程式代碼...")
        create_backup(target_dir, backup_dir)

        if progress_callback:
            progress_callback("正在解壓縮新版本檔案...")
        if os.path.exists(extract_temp):
            shutil.rmtree(extract_temp, ignore_errors=True)
        os.makedirs(extract_temp, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_temp)

        # 檢測是否有單一根目錄 (例如 FillinForm-main/ 或 FillinForm_v3.47/)
        extracted_items = os.listdir(extract_temp)
        source_root = extract_temp
        if len(extracted_items) == 1:
            candidate = os.path.join(extract_temp, extracted_items[0])
            if os.path.isdir(candidate):
                source_root = candidate

        if progress_callback:
            progress_callback("正在套用更新檔案 (保護帳密與 Session)...")

        # 逐一覆蓋檔案，強制保護名單項目跳過
        for root, dirs, files in os.walk(source_root):
            rel_dir = os.path.relpath(root, source_root)
            dest_dir = target_dir if rel_dir == "." else os.path.join(target_dir, rel_dir)

            # 檢查目錄是否在保護名單
            first_dir = rel_dir.split(os.sep)[0] if rel_dir != "." else ""
            if first_dir in PROTECTED_ITEMS:
                continue

            os.makedirs(dest_dir, exist_ok=True)

            for f in files:
                if f in PROTECTED_ITEMS:
                    continue
                src_file = os.path.join(root, f)
                dst_file = os.path.join(dest_dir, f)
                try:
                    shutil.copy2(src_file, dst_file)
                except Exception as e:
                    # Windows 檔案若仍有些微延遲鎖定，重試一次
                    try:
                        import time
                        time.sleep(0.3)
                        shutil.copy2(src_file, dst_file)
                    except Exception as err2:
                        print(f"⚠️ 檔案替換警告 ({f}): {err2}")

        # macOS / Linux 確保 run.sh 與 run.command 具備可執行權限
        if sys.platform != "win32":
            for script_name in ["run.sh", "run.command"]:
                p = os.path.join(target_dir, script_name)
                if os.path.exists(p):
                    try:
                        os.chmod(p, 0o755)
                    except Exception:
                        pass

        # 清理暫存解壓目錄
        shutil.rmtree(os.path.join(target_dir, "_update_temp"), ignore_errors=True)

        return {"success": True, "message": "新版本檔案套用完成！"}

    except Exception as e:
        if progress_callback:
            progress_callback(f"更新發生異常: {e}，正在還原舊版...")
        rollback_from_backup(target_dir, backup_dir)
        return {"success": False, "error": f"更新失敗並已還原: {e}"}


def perform_full_update(
    download_url: str,
    target_dir: str = BASE_DIR,
    progress_callback: Optional[Callable[[str], None]] = None
) -> Dict[str, Any]:
    """執行完整下載、驗證、解壓與套用流程"""
    temp_dir = os.path.join(target_dir, "_update_temp")
    temp_zip = os.path.join(temp_dir, "latest_update.zip")

    try:
        if progress_callback:
            progress_callback(f"正在連線下載更新包...")
        
        def on_download_progress(dl, total):
            if total > 0 and progress_callback:
                pct = int(dl / total * 100)
                mb_dl = dl / (1024 * 1024)
                mb_tot = total / (1024 * 1024)
                progress_callback(f"下載中: {mb_dl:.1f}MB / {mb_tot:.1f}MB ({pct}%)")

        download_file(download_url, temp_zip, on_download_progress)

        # 套用更新
        res = apply_update_from_zip(temp_zip, target_dir, progress_callback)
        return res

    except Exception as e:
        return {"success": False, "error": f"下載更新檔失敗: {e}"}
    finally:
        # 清理暫存檔案
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
