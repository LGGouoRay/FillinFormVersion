"""
FillinForm - Google Sheets 學生報告資訊讀取與驗證模組
唯讀同步指定試算表中的學生報告狀況：
五大欄位：順序、學號、姓名、報告與否、報告順序
"""

import os
import io
import csv
import json
import time
import hashlib
import asyncio
import re
from typing import Dict, Any, List, Optional, Tuple
import requests

from core.students_data import STUDENT_MAP
from core.version import APP_VERSION, DEFAULT_DRIVE_DOWNLOAD_URL

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE_PATH = os.path.join(BASE_DIR, "sheets_report_cache.json")

DEFAULT_SPREADSHEET_ID = "1GYqBknTIPjATyISIBp27cTeSqxplwQu40iFCvGaswn4"
DEFAULT_GID = "486059922"
DEFAULT_EXPORT_URL = (
    f"https://docs.google.com/spreadsheets/d/{DEFAULT_SPREADSHEET_ID}/export?format=csv&gid={DEFAULT_GID}"
)

REQUIRED_COLUMNS = ["學號", "姓名", "報告與否"]


def is_version_outdated(local_ver: str, remote_ver: Optional[str]) -> bool:
    """判斷本地版本是否落後於雲端版本 (支援語意化版本與小數版本)"""
    if not remote_ver:
        return False
    clean_local = re.sub(r"^[^\d]*", "", str(local_ver).strip())
    clean_remote = re.sub(r"^[^\d]*", "", str(remote_ver).strip())
    if not clean_remote or clean_local == clean_remote:
        return False

    # 若兩者為簡單小數形式 (如 3.46 與 3.47 或 3.5)
    try:
        if clean_local.count(".") == 1 and clean_remote.count(".") == 1:
            fl_local = float(clean_local)
            fl_remote = float(clean_remote)
            if fl_local != fl_remote:
                return fl_local < fl_remote
    except Exception:
        pass

    # 通用多段比對 (如 3.46.1 或 4.0.0)
    def to_tuple(clean_str):
        parts = re.split(r"[\.-]", clean_str)
        nums = []
        for p in parts:
            if p.isdigit():
                nums.append(int(p))
            else:
                break
        return tuple(nums) if nums else (0,)

    t_local = to_tuple(clean_local)
    t_remote = to_tuple(clean_remote)
    max_len = max(len(t_local), len(t_remote))
    t_local = t_local + (0,) * (max_len - len(t_local))
    t_remote = t_remote + (0,) * (max_len - len(t_remote))
    return t_local < t_remote



class SheetsReportManager:
    """Google Sheets 學生報告資訊唯讀管理員"""

    def __init__(
        self,
        csv_url: Optional[str] = None,
        poll_interval: int = 30,
        timeout: int = 10,
        cache_file: str = CACHE_FILE_PATH,
    ):
        self.custom_csv_url = csv_url
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.cache_file = cache_file

        self.local_version = APP_VERSION
        self.latest_version = APP_VERSION
        self.is_outdated = False
        self.download_url = DEFAULT_DRIVE_DOWNLOAD_URL
        self.changelog = ""

        self.current_data: List[Dict[str, Any]] = []
        self.current_hash: str = ""
        self.last_updated: float = 0.0
        self.last_sync_time_str: str = ""
        self.status: str = "empty"  # "live" | "cached" | "empty"
        self.error_message: Optional[str] = None

        self._lock = asyncio.Lock()
        self._polling_task: Optional[asyncio.Task] = None

    def get_csv_url(self) -> str:
        """取得有效的 CSV 下載網址（支援自訂或預設 Export URL）"""
        if self.custom_csv_url and self.custom_csv_url.strip():
            return self.custom_csv_url.strip()
        return DEFAULT_EXPORT_URL

    def set_csv_url(self, url: Optional[str]):
        """動態更新自訂 CSV URL"""
        self.custom_csv_url = url.strip() if url else None

    def load_disk_cache(self) -> bool:
        """啟動時自本機磁碟載入先前有效的快取資料與版本資訊"""
        if not os.path.exists(self.cache_file):
            return False
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            data = cached.get("data", [])
            if isinstance(data, list) and len(data) > 0:
                self.current_data = data
                self.current_hash = cached.get("hash", "")
                self.latest_version = cached.get("latest_version", self.local_version)
                self.download_url = cached.get("download_url", DEFAULT_DRIVE_DOWNLOAD_URL)
                self.changelog = cached.get("changelog", "")
                self.is_outdated = is_version_outdated(self.local_version, self.latest_version)
                self.last_updated = cached.get("last_updated", time.time())
                self.last_sync_time_str = time.strftime(
                    "%H:%M:%S", time.localtime(self.last_updated)
                )
                self.status = "cached"
                self.error_message = None
                return True
        except Exception as e:
            print(f"⚠️ [SheetsReport] 載入快取失敗: {e}")
        return False

    def save_disk_cache(self):
        """將目前有效的資料寫入本機快取檔案"""
        try:
            cache_payload = {
                "hash": self.current_hash,
                "last_updated": self.last_updated,
                "latest_version": self.latest_version,
                "download_url": self.download_url,
                "changelog": self.changelog,
                "data": self.current_data,
            }
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ [SheetsReport] 儲存快取至磁碟失敗: {e}")

    @staticmethod
    def extract_sheet_metadata(raw_csv_text: str) -> Dict[str, Any]:
        """
        從 Google Sheets CSV 標題列與資料列提取系統元資料：
        包含：目前版本號、下載連結/載點、更新說明/公告
        """
        metadata = {
            "latest_version": None,
            "download_url": None,
            "changelog": None,
        }
        try:
            reader = csv.reader(io.StringIO(raw_csv_text))
            rows = list(reader)
            if not rows:
                return metadata

            header = [col.strip() for col in rows[0]]
            col_map = {name: idx for idx, name in enumerate(header)}

            # 1. 尋找版本號欄位 (圖中欄位 F: 目前版本號)
            for k in ["目前版本號", "最新版本號", "版本號", "版本", "version"]:
                if k in col_map:
                    idx = col_map[k]
                    for r in rows[1:]:
                        if idx < len(r) and r[idx].strip():
                            metadata["latest_version"] = r[idx].strip()
                            break
                    break

            # 2. 尋找下載連結/載點欄位
            for k in ["下載連結", "下載網址", "載點", "雲端連結", "download_url"]:
                if k in col_map:
                    idx = col_map[k]
                    for r in rows[1:]:
                        if idx < len(r) and r[idx].strip():
                            metadata["download_url"] = r[idx].strip()
                            break
                    break

            # 3. 尋找更新說明欄位
            for k in ["更新說明", "版本說明", "更新日誌", "更新公告", "changelog"]:
                if k in col_map:
                    idx = col_map[k]
                    for r in rows[1:]:
                        if idx < len(r) and r[idx].strip():
                            metadata["changelog"] = r[idx].strip()
                            break
                    break

        except Exception as e:
            print(f"⚠️ [SheetsReport] 提取試算表元資料失敗: {e}")

        return metadata


    @staticmethod
    def parse_and_validate_csv(raw_csv_text: str) -> Tuple[bool, List[Dict[str, Any]], Optional[str]]:
        """
        嚴格解析與校驗 CSV 內容。
        依據五大欄位規則進行檢查，若有任何不合規處立即返回清晰錯誤指引（列號與欄位）。
        """
        try:
            reader = csv.reader(io.StringIO(raw_csv_text))
            rows_raw = list(reader)
        except Exception as e:
            return False, [], f"CSV 格式解析失敗: {e}"

        if not rows_raw:
            return False, [], "CSV 內容為空"

        # 1. 欄位名稱對應 (以名稱匹配，不以索引位置)
        header = [col.strip() for col in rows_raw[0]]
        col_map = {name: idx for idx, name in enumerate(header)}

        missing_cols = [c for c in REQUIRED_COLUMNS if c not in col_map]
        if missing_cols:
            return False, [], f"第 1 列缺少必要欄位名稱: {', '.join(missing_cols)}"

        idx_sid = col_map["學號"]
        idx_name = col_map["姓名"]
        idx_reported = col_map["報告與否"]
        idx_order = col_map.get("順序")
        idx_report_order = col_map.get("報告順序")
        idx_group = col_map.get("報告組別") or col_map.get("組別")

        validated_rows: List[Dict[str, Any]] = []
        seen_sids = set()
        seen_report_orders: Dict[int, int] = {}  # report_order -> row_num

        # 2. 資料列逐行校驗 (第 1 列為標題，資料自第 2 列開始)
        for row_num, row in enumerate(rows_raw[1:], start=2):
            # 忽略完全空白的列
            if not any(cell.strip() for cell in row):
                continue

            # 安全取出各欄字串
            def get_cell(idx: Optional[int]) -> str:
                if idx is None:
                    return ""
                return row[idx].strip() if idx < len(row) else ""

            val_sid = get_cell(idx_sid)
            val_name = get_cell(idx_name)
            val_reported = get_cell(idx_reported)
            val_order = get_cell(idx_order)
            val_report_order = get_cell(idx_report_order)
            val_group = get_cell(idx_group)

            # 規則 1: 順序 (若標題有「順序」欄位則不可為空且必須為正整數；若試算表未提供此欄位則預設以列號遞增)
            if idx_order is not None:
                if not val_order:
                    return False, [], f"第 {row_num} 列：「順序」欄位不可為空"
                if not (val_order.isdigit() and int(val_order) > 0):
                    return False, [], f"第 {row_num} 列：「順序」必須為正整數，實際為「{val_order}」"
                order_int = int(val_order)
            else:
                order_int = row_num - 1

            # 規則 2: 學號 (去除空白字串，不可為空，同一份資料不能重複)
            if not val_sid:
                return False, [], f"第 {row_num} 列：「學號」欄位不可為空"
            if val_sid in seen_sids:
                return False, [], f"第 {row_num} 列：「學號」【{val_sid}】重複出現，試算表不得包含重複學號"
            seen_sids.add(val_sid)

            # 規則 3: 姓名 (純顯示，不可為空)
            if not val_name:
                return False, [], f"第 {row_num} 列：「姓名」欄位不可為空"

            # 規則 4: 報告與否 (只接受「未報告」與「已報告」)
            if not val_reported:
                return False, [], f"第 {row_num} 列：「報告與否」欄位不可為空"
            if val_reported not in ["未報告", "已報告"]:
                return (
                    False,
                    [],
                    f"第 {row_num} 列：「報告與否」僅接受「未報告」或「已報告」，實際為「{val_reported}」",
                )

            # 規則 5: 報告順序 (正整數或空白，空白表示尚未設定)
            report_order_int: Optional[int] = None
            if val_report_order:
                if not (val_report_order.isdigit() and int(val_report_order) > 0):
                    return (
                        False,
                        [],
                        f"第 {row_num} 列：「報告順序」必須為正整數或空白，實際為「{val_report_order}」",
                    )
                report_order_int = int(val_report_order)
                # 第一版非空報告順序重複視為資料錯誤
                if report_order_int in seen_report_orders:
                    orig_row = seen_report_orders[report_order_int]
                    return (
                        False,
                        [],
                        f"第 {row_num} 列：「報告順序」【{report_order_int}】與第 {orig_row} 列重複",
                    )
                seen_report_orders[report_order_int] = row_num

            # 組別歸屬 (優先讀取試算表「報告組別」，未填則依附錄名冊 fallback)
            group_val = None
            if val_group:
                if val_group.isdigit():
                    group_val = int(val_group)
                else:
                    group_val = val_group
            else:
                student_info = STUDENT_MAP.get(val_sid.upper())
                if student_info:
                    group_val = student_info.get("group", 1)
                else:
                    group_val = 1

            validated_rows.append({
                "order": order_int,
                "student_id": val_sid,
                "name": val_name,
                "reported": val_reported,
                "report_order": report_order_int,
                "group": group_val,
            })

        # 依「順序」由小到大排序
        validated_rows.sort(key=lambda item: item["order"])
        return True, validated_rows, None

    def fetch_remote_csv(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """透過 HTTP 下載遠端 Google Sheets 唯讀 CSV (帶超時防禦)"""
        url = self.get_csv_url()
        try:
            resp = requests.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/csv, text/plain, */*",
                },
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return False, None, f"HTTP 回應錯誤狀態碼: {resp.status_code}"

            content_type = resp.headers.get("Content-Type", "").lower()
            if "html" in content_type and "csv" not in content_type:
                return (
                    False,
                    None,
                    "取得內容為 HTML 頁面而非資料串流，請確認連線網址或共用權限已設為公開查看",
                )

            # 支援 utf-8 與 utf-8-sig
            text = resp.content.decode("utf-8-sig", errors="replace")
            return True, text, None
        except requests.Timeout:
            return False, None, f"連線雲端資料庫超時 (超過 {self.timeout} 秒)"
        except Exception as e:
            return False, None, f"連線失敗: {str(e)}"

    async def update_once(self) -> Tuple[bool, bool]:
        """
        執行一次抓取、驗證與狀態更新 (協同鎖防重疊)。
        返回: (is_success, has_content_changed)
        """
        async with self._lock:
            # 1. 遠端下載
            loop = asyncio.get_event_loop()
            ok, raw_text, err = await loop.run_in_executor(None, self.fetch_remote_csv)

            if not ok:
                # 下載失敗：保留現有快取，切換狀態
                self.error_message = err
                if self.current_data:
                    self.status = "cached"
                else:
                    self.status = "empty"
                return False, False

            # 提取試算表元資料 (版本號、下載連結等)
            meta = self.extract_sheet_metadata(raw_text)
            meta_changed = False
            if meta.get("latest_version") and meta["latest_version"] != self.latest_version:
                self.latest_version = meta["latest_version"]
                self.is_outdated = is_version_outdated(self.local_version, self.latest_version)
                meta_changed = True
            if meta.get("download_url") and meta["download_url"] != self.download_url:
                self.download_url = meta["download_url"]
                meta_changed = True
            if meta.get("changelog") and meta["changelog"] != self.changelog:
                self.changelog = meta["changelog"]
                meta_changed = True

            # 2. 驗證與解析
            valid, rows, val_err = self.parse_and_validate_csv(raw_text)
            if not valid:
                # 驗證失敗：不覆蓋既有有效快取！
                self.error_message = val_err
                if self.current_data:
                    self.status = "cached"
                else:
                    self.status = "empty"
                return False, False

            # 3. 內容雜湊比對
            canonical_json = json.dumps(rows, sort_keys=True, ensure_ascii=False)
            new_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

            has_changed = False
            if new_hash != self.current_hash or not self.current_data or meta_changed:
                has_changed = True
                self.current_data = rows
                self.current_hash = new_hash
                self.save_disk_cache()

            self.last_updated = time.time()
            self.last_sync_time_str = time.strftime(
                "%H:%M:%S", time.localtime(self.last_updated)
            )
            self.status = "live"
            self.error_message = None
            return True, has_changed

    def get_payload(self) -> Dict[str, Any]:
        """產出傳遞給前端顯示的標準資料包"""
        reported_count = sum(
            1 for s in self.current_data if s.get("reported") == "已報告"
        )

        # 依組別彙整已報告的學生 (未報告不顯示)
        groups_map: Dict[Any, Dict[str, Any]] = {}
        for item in self.current_data:
            if item.get("reported") != "已報告":
                continue
            gid = item.get("group", 1)
            if gid not in groups_map:
                groups_map[gid] = {
                    "group_id": gid,
                    "group_name": f"第 {gid} 組",
                    "status": "已報告",
                    "members": [],
                }
            groups_map[gid]["members"].append({
                "student_id": item["student_id"],
                "name": item["name"],
                "report_order": item.get("report_order"),
                "order": item.get("order"),
            })

        # 組別依序排序
        groups_list: List[Dict[str, Any]] = []
        for gid in sorted(groups_map.keys(), key=lambda x: (int(x) if str(x).isdigit() else str(x))):
            g_item = groups_map[gid]
            groups_list.append(g_item)

        return {
            "status": self.status,  # "live" | "cached" | "empty"
            "last_sync_time": self.last_sync_time_str,
            "last_updated_timestamp": self.last_updated,
            "error": self.error_message,
            "data": self.current_data,
            "groups": groups_list,
            "total_count": len(self.current_data),
            "reported_count": reported_count,
            "poll_interval": self.poll_interval,
            "csv_url": self.get_csv_url(),
            "version_info": {
                "local_version": self.local_version,
                "latest_version": self.latest_version or self.local_version,
                "is_outdated": self.is_outdated,
                "download_url": self.download_url or DEFAULT_DRIVE_DOWNLOAD_URL,
                "changelog": self.changelog or "",
            },
        }

    async def start_background_polling(self, on_update_callback):
        """啟動定時輪詢背景協程（預設每 30 秒）"""
        print(f"📊 [CloudSync] 啟動背景同步任務 (輪詢間隔: {self.poll_interval}s)...", flush=True)

        # 首次啟動立即執行一次更新
        try:
            ok, changed = await self.update_once()
            await on_update_callback(self.get_payload(), force=True)
        except Exception as e:
            print(f"⚠️ [CloudSync] 首次同步提示: {e}", flush=True)

        while True:
            try:
                await asyncio.sleep(self.poll_interval)
                ok, changed = await self.update_once()
                # 只有當資料變更或狀態產生變化時，才觸發前端更新推播
                if changed or not ok:
                    await on_update_callback(self.get_payload(), force=False)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"⚠️ [CloudSync] 背景輪詢提示: {e}", flush=True)
                await asyncio.sleep(5)
