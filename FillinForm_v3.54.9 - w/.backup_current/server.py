"""
FillinForm - 主微伺服器 (FastAPI / Uvicorn)
僅綁定 127.0.0.1 本機迴環地址。
提供即時四等分 WebSocket 畫面串流、真實瀏覽器控制、分數正規化、四站安全送出與 Dry-Run 演練機制。
"""

import os
import re
import sys
import json
import time
import asyncio
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from core.score_engine import ScoreEngine, sanitize_score
from core.students_data import (
    STUDENTS,
    get_all_students,
    get_student_by_id,
    validate_evaluation_target,
    validate_group_bounds,
)
from core.chatgpt_client import ChatGPTClient
from core.firebase_client import FirebaseGradingClient
from core.googleform_client import GoogleFormClient
from core.nla_client import NLAClient
from core.browser_manager import BrowserManager
from core.sheets_client import SheetsReportManager
from core.version import APP_VERSION, APP_TITLE, DEFAULT_DRIVE_DOWNLOAD_URL, GITHUB_OWNER, GITHUB_REPO
from core.updater import check_github_latest

CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


def load_credentials() -> Dict[str, Any]:
    """載入憑證（僅讀取本專案目錄）"""
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "student_id": "",
        "student_name": "",
        "email": "",
        "stanleyowen_email": "",
        "stanleyowen_password": "",
        "nla_password": "",
        "nla_task_id": "1b4043962c20452db349429f88337822",
        "sheets_csv_url": "",
    }


def save_credentials(data: Dict[str, Any]):
    """儲存憑證"""
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# 全域實例初始化
chatgpt_client = ChatGPTClient()
firebase_client = FirebaseGradingClient()
googleform_client = GoogleFormClient()
nla_client = NLAClient()
sheets_manager = SheetsReportManager()

# 是否開啟 headed 模式（預設 headed 讓真實瀏覽器可見並手動介入）
is_headless = os.getenv("HEADLESS", "0") == "1"
browser_manager = BrowserManager(headless=is_headless)

# 評分提交中狀態旗標 (防止提交途中更新導致資料中斷)
is_submitting_active = False

# GitHub 版本快取與定時檢查任務
latest_version_cache: Dict[str, Any] = {}
version_check_task: Optional[asyncio.Task] = None

# WebSocket 連線管理
active_websockets: List[WebSocket] = []
stream_task: Optional[asyncio.Task] = None


async def broadcast_version_updates():
    """背景定時檢查雲端版本 (每 10 分鐘一次)，若有新版主動推播至所有儀表板"""
    global latest_version_cache
    while True:
        try:
            info = check_github_latest(owner=GITHUB_OWNER, repo=GITHUB_REPO, timeout=5)
            latest_version_cache = info
            if info.get("has_update") and active_websockets:
                msg = json.dumps({"type": "version_update", "data": info})
                for ws in list(active_websockets):
                    try:
                        await ws.send_text(msg)
                    except Exception:
                        pass
        except Exception:
            pass
        await asyncio.sleep(600)


async def broadcast_screen_frames():
    """背景定時向所有連線的儀表板推播 4 分割即時畫面 (約每 500ms 一次)"""
    counter = 0
    s3_needs_login = False
    while True:
        try:
            if active_websockets and browser_manager.is_running:
                frames = await browser_manager.capture_all_screenshots_base64()
                counter += 1
                if counter % 3 == 0:
                    s3_needs_login = await browser_manager.check_s3_needs_login()

                payload = json.dumps({
                    "type": "quad_stream",
                    "frames": frames,
                    "s3_needs_login": s3_needs_login,
                })
                dead_sockets = []
                for ws in active_websockets:
                    try:
                        await ws.send_text(payload)
                    except Exception:
                        dead_sockets.append(ws)
                for ds in dead_sockets:
                    if ds in active_websockets:
                        active_websockets.remove(ds)
        except Exception:
            pass
        await asyncio.sleep(0.5)


async def broadcast_fill_status(site: str, status: str, detail: str = ""):
    """即時向所有連線的儀表板推送平台填寫狀態 (idle / filling / completed / error)"""
    payload = json.dumps({
        "type": "fill_status",
        "site": site,
        "status": status,
        "detail": detail,
        "timestamp": asyncio.get_event_loop().time(),
    })
    dead_sockets = []
    for ws in list(active_websockets):
        try:
            await ws.send_text(payload)
        except Exception:
            dead_sockets.append(ws)
    for ds in dead_sockets:
        if ds in active_websockets:
            active_websockets.remove(ds)


async def broadcast_sheets_update(payload: Dict[str, Any], force: bool = False):
    """推播 Google Sheets 學生報告資訊更新 (局部通知，無打斷操作)"""
    msg = json.dumps({
        "type": "sheets_report_update",
        **payload,
    })
    dead_sockets = []
    for ws in list(active_websockets):
        try:
            await ws.send_text(msg)
        except Exception:
            dead_sockets.append(ws)
    for ds in dead_sockets:
        if ds in active_websockets:
            active_websockets.remove(ds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 啟動時：初始化瀏覽器與推播任務
    print(f"🚀 [FillinForm v{APP_VERSION}] 啟動伺服器與核心引擎...", flush=True)
    creds = load_credentials()
    browser_manager.update_credentials(creds)
    try:
        await browser_manager.start()
        print("✅ 核心自動化引擎已就緒，4 大平台頁面已載入！", flush=True)
        sid = creds.get("student_id", "")
        if sid:
            s_name = creds.get("student_name", "")
            fb_email = creds.get("stanleyowen_email", f"{sid.lower()}@mail.ntust.edu.tw")
            fb_pwd = creds.get("stanleyowen_password", "")
            nla_pwd = creds.get("nla_password", "")
            nla_task = creds.get("nla_task_id", "1b4043962c20452db349429f88337822")
            print(f"🔑 正在為使用者 ({sid}) 自動同步 S1 姓名確認與四大平台登入狀態...", flush=True)
            asyncio.create_task(browser_manager.perform_initial_logins(
                student_id=sid,
                student_name=s_name,
                fb_email=fb_email,
                fb_pwd=fb_pwd,
                nla_pwd=nla_pwd,
                nla_task_id=nla_task,
            ))
        if os.environ.get("LAUNCHER_RESTARTED") != "1":
            import webbrowser
            webbrowser.open("http://127.0.0.1:8000")
        else:
            print("🔄 已完成熱更新重新啟動，沿用現有瀏覽器分頁！", flush=True)
    except Exception as e:
        print(f"⚠️ 核心引擎啟動提示: {e}", flush=True)

    # 啟動雲端資料庫背景同步任務
    sheets_task = None
    try:
        sheets_manager.load_disk_cache()
        custom_csv = creds.get("sheets_csv_url") or os.getenv("SHEETS_CSV_URL")
        if custom_csv:
            sheets_manager.set_csv_url(custom_csv)
        sheets_task = asyncio.create_task(
            sheets_manager.start_background_polling(broadcast_sheets_update)
        )
    except Exception as e:
        print(f"⚠️ [CloudSync] 啟動提示: {e}", flush=True)

    global stream_task, version_check_task
    stream_task = asyncio.create_task(broadcast_screen_frames())
    version_check_task = asyncio.create_task(broadcast_version_updates())

    yield

    # 關閉時：關閉瀏覽器與清理任務
    if stream_task:
        stream_task.cancel()
    if version_check_task:
        version_check_task.cancel()
    if sheets_task:
        sheets_task.cancel()
    await browser_manager.stop()
    print(f"👋 [FillinForm v{APP_VERSION}] 伺服器已平穩關閉。", flush=True)


app = FastAPI(title="FillinForm Server", lifespan=lifespan)

# 安全鎖定：僅允許本機 127.0.0.1 存取
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 強制防快取中介層：確保使用者與同學每次開啟或更新時，瀏覽器必定載入最新 CSS/JS
@app.middleware("http")
async def add_anti_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/screenshots", StaticFiles(directory=SCREENSHOTS_DIR), name="screenshots")


# ==================== API 路由 ====================

@app.get("/")
def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            html_content = f.read()
        # 自動為所有 /static/ 檔案注入版本號快取破壞參數 (Cache-Busting Query String)
        html_content = re.sub(
            r'((?:href|src)=["\']/static/[^"\']+\.(?:css|js))(?:\?[^"\']*)?(["\'])',
            rf'\1?v={APP_VERSION}\2',
            html_content
        )
        return HTMLResponse(
            content=html_content,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        )
    return HTMLResponse("<h1>FillinForm Dashboard Ready</h1>")


@app.get("/api/admin/stats")
def dummy_admin_stats():
    """靜默攔截外部舊分頁探測，防止 404 訊息洗版"""
    return {"status": "ok", "app": "FillinForm", "version": APP_VERSION}


@app.get("/api/config")
def get_config():
    """取得脫敏帳號設定"""
    creds = load_credentials()
    sid = creds.get("student_id", "")
    s2_pwd = creds.get("stanleyowen_password", "")
    s4_pwd = creds.get("nla_password", "")
    is_first_time = not (bool(sid) and bool(s2_pwd) and bool(s4_pwd))
    return {
        "app_version": APP_VERSION,
        "student_id": sid,
        "student_name": creds.get("student_name", ""),
        "email": creds.get("email", ""),
        "stanleyowen_email": creds.get("stanleyowen_email", f"{sid.lower()}@mail.ntust.edu.tw" if sid else ""),
        "has_stanleyowen_password": bool(s2_pwd),
        "has_nla_password": bool(s4_pwd),
        "nla_task_id": creds.get("nla_task_id", "1b4043962c20452db349429f88337822"),
        "is_first_time": is_first_time,
    }


@app.get("/api/system/update_status")
def get_system_update_status():
    """查詢 GitHub Releases 最新版本資訊"""
    global latest_version_cache
    info = check_github_latest(owner=GITHUB_OWNER, repo=GITHUB_REPO, timeout=5)
    latest_version_cache = info
    return info


@app.post("/api/system/request_update")
async def request_system_update(data: Optional[Dict[str, Any]] = None):
    """
    網頁端發起「更新並重新啟動」請求：
    1. 防呆檢查：若正在提交資料則拒絕更新
    2. 寫入 .update_requested 標記檔
    3. 觸發優雅關閉並送出信號 Code 42 由 launcher.py 接手執行更新與重啟
    """
    global is_submitting_active
    if is_submitting_active:
        raise HTTPException(status_code=400, detail="目前系統正在進行評分提交，為保護資料安全，請於提交完成後再進行更新！")

    payload = data or {}
    download_url = payload.get("download_url")
    target_version = payload.get("target_version")

    # 若未指定 download_url，向雲端發布伺服器查詢
    if not download_url:
        latest = check_github_latest(owner=GITHUB_OWNER, repo=GITHUB_REPO, timeout=5)
        download_url = latest.get("download_url")
        target_version = latest.get("latest_version")

    flag_file = os.path.join(BASE_DIR, ".update_requested")
    try:
        with open(flag_file, "w", encoding="utf-8") as f:
            json.dump({
                "download_url": download_url,
                "target_version": target_version,
                "requested_at": time.time(),
            }, f, indent=2)
    except Exception as e:
        print(f"⚠️ 寫入更新標記失敗: {e}")

    async def _graceful_exit():
        await asyncio.sleep(0.5)
        try:
            await browser_manager.stop()
        except Exception:
            pass
        os._exit(42)

    asyncio.create_task(_graceful_exit())
    return {"status": "success", "message": "已成功送出更新請求，伺服器正在準備重啟..."}


@app.get("/api/query_name")
def query_name_by_id(id: str):
    """依學號查詢 S1 或內建表學生姓名"""
    cleaned_id = id.strip().upper()
    try:
        info = chatgpt_client.get_student_info(cleaned_id)
        name = info.get("student", {}).get("name")
        if name:
            return {"status": "success", "name": name, "source": "S1"}
    except Exception:
        pass
    st = get_student_by_id(cleaned_id)
    if st:
        return {"status": "success", "name": st["name"], "source": "local"}
    return {"status": "not_found", "name": "", "message": "查無此學號"}


@app.post("/api/setup")
async def setup_accounts(data: Dict[str, Any]):
    """
    首次使用設定或更新帳號密碼，並於四大平台進行即時連線與登入校驗
    """
    student_id = data.get("student_id", "").strip().upper()
    student_name = data.get("student_name", "").strip()
    email = data.get("email", "").strip()
    stanleyowen_email = data.get("stanleyowen_email", "").strip() or f"{student_id.lower()}@mail.ntust.edu.tw"
    stanleyowen_password = data.get("stanleyowen_password", "").strip()
    nla_password = data.get("nla_password", "").strip()
    nla_task_id = data.get("nla_task_id", "").strip() or "1b4043962c20452db349429f88337822"

    if not student_id:
        raise HTTPException(status_code=400, detail="請填寫學號！")

    checks = {}
    errors = []

    # S1 檢查
    try:
        s1_info = chatgpt_client.get_student_info(student_id)
        checks["S1"] = True
        if not student_name:
            student_name = s1_info.get("student", {}).get("name", "")
    except Exception as e:
        checks["S1"] = False
        errors.append(f"S1 查詢失敗: {e}")

    # S2 檢查 (Firebase)
    if stanleyowen_password:
        try:
            firebase_client.login(stanleyowen_email, stanleyowen_password)
            checks["S2"] = True
        except Exception as e:
            checks["S2"] = False
            errors.append(f"S2 Firebase 登入失敗: {e}")
    else:
        checks["S2"] = False
        errors.append("S2 未提供密碼")

    # S3 檢查 (Google 表單連線)
    try:
        opts = googleform_client.get_candidate_options()
        s3_needs_login = await browser_manager.check_s3_needs_login()
        checks["S3_login_needed"] = s3_needs_login
        checks["S3"] = (not s3_needs_login) and (len(opts) > 0)
    except Exception as e:
        checks["S3"] = False
        checks["S3_login_needed"] = True
        errors.append(f"S3 表單連線失敗: {e}")

    # S4 檢查 (NLA)
    if nla_password:
        try:
            nla_client.login(student_id, nla_password)
            checks["S4"] = True
        except Exception as e:
            checks["S4"] = False
            errors.append(f"S4 NLA 登入失敗: {e}")
    else:
        checks["S4"] = False
        errors.append("S4 未提供密碼")

    # 儲存至憑證檔
    new_creds = {
        "student_id": student_id,
        "student_name": student_name,
        "email": email,
        "stanleyowen_email": stanleyowen_email,
        "stanleyowen_password": stanleyowen_password,
        "nla_password": nla_password,
        "nla_task_id": nla_task_id,
    }
    save_credentials(new_creds)
    browser_manager.update_credentials(new_creds)

    # 在 Playwright 真實瀏覽器中同步執行登入以持久化 Session
    if browser_manager.is_running:
        await browser_manager.perform_initial_logins(
            student_id=student_id,
            student_name=student_name,
            fb_email=stanleyowen_email,
            fb_pwd=stanleyowen_password,
            nla_pwd=nla_password,
            nla_task_id=nla_task_id,
        )

    return {
        "status": "success" if not errors else "partial_success",
        "checks": checks,
        "errors": errors,
        "student_name": student_name,
        "student_id": student_id,
        "message": "登入與四大平台驗證完成！" if not errors else "已儲存設定，但部分平台驗證提示：" + "；".join(errors),
    }


@app.post("/api/config")
def update_config(data: Dict[str, Any]):
    """更新帳號設定"""
    creds = load_credentials()
    for k in ["student_id", "student_name", "email", "stanleyowen_email", "nla_task_id"]:
        if k in data and data[k]:
            creds[k] = data[k]
    if "stanleyowen_password" in data and data["stanleyowen_password"]:
        creds["stanleyowen_password"] = data["stanleyowen_password"]
    if "nla_password" in data and data["nla_password"]:
        creds["nla_password"] = data["nla_password"]
    save_credentials(creds)
    browser_manager.update_credentials(creds)
    return {"status": "success", "message": "設定已更新"}


@app.get("/api/students")
def get_students_list():
    """
    取得 29 位同學清單、組別與即時互評完成狀態
    """
    creds = load_credentials()
    my_id = creds.get("student_id", "")

    # 取得 NLA 完成狀態
    nla_completed_map = {}
    if creds.get("nla_password"):
        try:
            nla_client.login(my_id, creds.get("nla_password"))
            assignments = nla_client.get_my_assignments(creds.get("nla_task_id", "1b4043962c20452db349429f88337822"))
            for a in assignments:
                t = a.get("target", {})
                sid = t.get("student_id", "").strip().upper()
                rev = a.get("review")
                if rev and rev.get("total_score") is not None:
                    nla_completed_map[sid] = rev.get("total_score")
        except Exception:
            pass

    # 取得 S1 已評組別
    s1_rated_groups = []
    try:
        s1_info = chatgpt_client.get_student_info(my_id)
        s1_rated_groups = s1_info.get("rated", [])
    except Exception:
        pass

    results = []
    for s in STUDENTS:
        sid = s["student_id"]
        is_self = (sid.upper() == my_id.upper())
        status = "self" if is_self else "pending"
        score = None

        if sid.upper() in nla_completed_map:
            status = "completed"
            score = nla_completed_map[sid.upper()]

        results.append({
            "student_id": sid,
            "name": s["name"],
            "group": s["group"],
            "status": status,
            "score": score,
            "is_self": is_self,
            "s1_group_rated": (s["group"] in s1_rated_groups)
        })

    return {"status": "success", "reviewer_id": my_id, "data": results}


@app.post("/api/calculate")
def calculate_scores(data: Dict[str, Any]):
    """
    依據第 4 章分數換算引擎，計算四平台向度換算結果
    """
    topic = data.get("topic", 80)
    content = data.get("content", 80)
    narrative = data.get("narrative", 80)
    presentation = data.get("presentation", 80)
    teamwork = data.get("teamwork", 80)

    res = ScoreEngine.calculate_all(topic, content, narrative, presentation, teamwork)
    return {"status": "success", "result": res}


@app.post("/api/bring_to_front")
async def bring_tab_to_front(data: Dict[str, Any]):
    """切換真實瀏覽器頁籤至最上層"""
    site = data.get("site", "S1").upper()
    success = await browser_manager.bring_to_front(site)
    return {"status": "success" if success else "failed", "site": site}


@app.get("/api/s3_status")
async def get_s3_status():
    """檢查 S3 Google 表單是否需要手動登入 Google 帳號"""
    needs_login = await browser_manager.check_s3_needs_login()
    return {"needs_login": needs_login}


@app.post("/api/s3_open_login")
async def open_s3_login():
    """在真實瀏覽器中開啟 S3 Google 登入畫面並帶到最上層"""
    success = await browser_manager.open_s3_google_login()
    return {"status": "success" if success else "failed"}


@app.post("/api/preview")
async def preview_fill(data: Dict[str, Any]):
    """
    「🪄 填寫預覽」：在 4 個真實 page 中填入向度與評語但不送出，並截圖回傳
    """
    creds = load_credentials()
    grader_id = creds.get("student_id", "")
    grader_name = creds.get("student_name", "")
    grader_email = creds.get("email", "")

    target_id = data.get("target_id", "")
    target_name = data.get("target_name", "")
    group_num = data.get("group", 1)
    scores = data.get("scores", {})
    comment = data.get("comment", "")

    # 自我互評防呆
    try:
        validate_evaluation_target(target_id, grader_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    group_num = validate_group_bounds(group_num)

    calc = ScoreEngine.calculate_all(
        scores.get("topic", 80),
        scores.get("content", 80),
        scores.get("narrative", 80),
        scores.get("presentation", 80),
        scores.get("teamwork", 80),
    )

    async def on_status_change(site: str, status: str, detail: str = ""):
        await broadcast_fill_status(site, status, detail)

    preview_res = await browser_manager.preview_fill_all(
        grader_id=grader_id,
        grader_name=grader_name,
        grader_email=grader_email,
        target_id=target_id,
        target_name=target_name,
        group_num=group_num,
        scores_payload=calc,
        comment=comment,
        status_callback=on_status_change,
    )

    evidence = preview_res.get("evidence_screenshots", {})
    skipped_sites = preview_res.get("skipped_sites", [])
    skipped_reasons = preview_res.get("skipped_reasons", {})

    status_str = "success"
    if skipped_sites:
        status_str = "partial_success"
        msg = f"預覽完成，部分未登入平台已自動跳過：{', '.join(skipped_sites)}。請點選頁籤登入！"
    else:
        msg = "已在四站完成填寫預覽（未送出）！"

    return {
        "status": status_str,
        "message": msg,
        "skipped_sites": skipped_sites,
        "skipped_reasons": skipped_reasons,
        "evidence_screenshots": evidence,
        "calculated_scores": calc,
    }


@app.post("/api/submit")
async def submit_evaluations(data: Dict[str, Any]):
    """
    「🚀 送出」：經使用者在覆核視窗核對後執行
    支援 Dry-Run 演練模式與指定排除平台。
    """
    global is_submitting_active
    creds = load_credentials()
    grader_id = creds.get("student_id", "")
    grader_name = creds.get("student_name", "")
    grader_email = creds.get("email", "")
    fb_email = creds.get("stanleyowen_email", f"{grader_id.lower()}@mail.ntust.edu.tw")
    fb_pwd = creds.get("stanleyowen_password", "")
    nla_pwd = creds.get("nla_password", "")
    nla_task_id = creds.get("nla_task_id", "1b4043962c20452db349429f88337822")

    target_id = data.get("target_id", "")
    target_name = data.get("target_name", "")
    group_num = data.get("group", 1)
    scores = data.get("scores", {})
    comment = data.get("comment", "")
    dry_run = data.get("dry_run", True)
    excluded = data.get("excluded_sites", [])

    # 防呆檢查 1：自我互評防呆
    try:
        validate_evaluation_target(target_id, grader_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 防呆檢查 2：組別越界防呆
    try:
        group_num = validate_group_bounds(group_num)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 計算向度換算
    calc = ScoreEngine.calculate_all(
        scores.get("topic", 80),
        scores.get("content", 80),
        scores.get("narrative", 80),
        scores.get("presentation", 80),
        scores.get("teamwork", 80),
    )

    # 防呆檢查 3：Google 表單受評者字串比對
    s3_option_text = None
    if "S3" not in excluded:
        try:
            s3_option_text = googleform_client.match_target_option(target_id, target_name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ==================== Dry-Run 演練模式 ====================
    if dry_run:
        return {
            "status": "dry_run_success",
            "message": "【Dry-Run 演練模式】所有向度換算與防呆檢驗 100% 通過！未向正式平台發送送出請求。",
            "target": {"id": target_id, "name": target_name, "group": group_num},
            "payloads_ready": {
                "S1": calc["chatgpt"],
                "S2": calc["stanleyowen"],
                "S3": {**calc["googleform"], "target_option": s3_option_text},
                "S4": calc["nla"],
            },
            "excluded_sites": excluded,
        }

    # ==================== 正式逐站送出 ====================
    is_submitting_active = True
    try:
        async def on_status_change(site: str, status: str, detail: str = ""):
            await broadcast_fill_status(site, status, detail)

        if browser_manager.is_running:
            submission_results = await browser_manager.submit_in_browser_all(
                grader_id=grader_id,
                grader_name=grader_name,
                grader_email=grader_email,
                target_id=target_id,
                target_name=target_name,
                group_num=group_num,
                scores_payload=calc,
                comment=comment,
                excluded_sites=excluded,
                status_callback=on_status_change,
                nla_task_id=nla_task_id,
            )
        else:
            submission_results = {}

            # 1. 送出 S1
            if "S1" not in excluded:
                try:
                    s1_res = chatgpt_client.submit_rating(
                        student_id=grader_id,
                        group_num=group_num,
                        scores=calc["chatgpt"],
                    )
                    submission_results["S1"] = {"success": True, "message": "S1 送出成功！", "data": s1_res}
                except Exception as e:
                    submission_results["S1"] = {"success": False, "error": str(e), "message": f"S1 送出失敗: {e}"}

            # 2. 送出 S2
            if "S2" not in excluded:
                try:
                    if not firebase_client.id_token:
                        firebase_client.login(fb_email, fb_pwd)
                    s2_res = firebase_client.submit_grade(
                        grader_id=grader_id,
                        target_id=target_id,
                        scores=calc["stanleyowen"],
                        comment=comment,
                    )
                    submission_results["S2"] = {"success": True, "message": "S2 送出成功！", "data": s2_res}
                except Exception as e:
                    submission_results["S2"] = {"success": False, "error": str(e), "message": f"S2 送出失敗: {e}"}

            # 3. 送出 S3
            if "S3" not in excluded:
                try:
                    s3_res = googleform_client.submit_form(
                        grader_name=grader_name,
                        grader_id=grader_id,
                        grader_email=grader_email,
                        target_option_text=s3_option_text,
                        scores=calc["googleform"],
                        comment=comment,
                    )
                    submission_results["S3"] = {"success": True, "message": "S3 送出成功！"}
                except Exception as e:
                    submission_results["S3"] = {"success": False, "error": str(e), "message": f"S3 送出失敗: {e}"}

            # 4. 送出 S4
            if "S4" not in excluded:
                try:
                    if not nla_client.token:
                        nla_client.login(grader_id, nla_pwd)
                    assignments = nla_client.get_my_assignments(nla_task_id)
                    assignment_id = None
                    for a in assignments:
                        t = a.get("target", {})
                        if t.get("student_id", "").strip().upper() == target_id.strip().upper():
                            assignment_id = a.get("id")
                            break

                    if not assignment_id:
                        raise ValueError(f"在 NLA 作業中找不到受評學號 {target_id} 的 Assignment ID")

                    s4_res = nla_client.submit_review(
                        assignment_id=assignment_id,
                        scores=calc["nla"],
                        comment=comment,
                    )
                    submission_results["S4"] = {"success": True, "message": "S4 送出成功！", "data": s4_res}
                except Exception as e:
                    submission_results["S4"] = {"success": False, "error": str(e), "message": f"S4 送出失敗: {e}"}

        return {
            "status": "completed",
            "target_id": target_id,
            "results": submission_results,
        }
    finally:
        is_submitting_active = False


# ==================== Google Sheets 學生報告資訊 API ====================

@app.get("/api/sheets_report")
def get_sheets_report():
    """取得當前已驗證之 Google Sheets 學生報告資訊（唯讀）"""
    return JSONResponse(sheets_manager.get_payload())


@app.post("/api/sheets_report/refresh")
async def refresh_sheets_report():
    """手動觸發立即同步 Google Sheets 報告狀態"""
    ok, changed = await sheets_manager.update_once()
    payload = sheets_manager.get_payload()
    await broadcast_sheets_update(payload, force=True)
    return JSONResponse(payload)


@app.get("/api/version")
def get_version_info():
    """取得應用程式版本號與 GitHub 最新更新資訊"""
    global latest_version_cache
    if not latest_version_cache:
        try:
            latest_version_cache = check_github_latest(owner=GITHUB_OWNER, repo=GITHUB_REPO, timeout=5)
        except Exception:
            pass

    return JSONResponse({
        "local_version": APP_VERSION,
        "latest_version": latest_version_cache.get("latest_version") or APP_VERSION,
        "is_outdated": latest_version_cache.get("has_update", False),
        "download_url": latest_version_cache.get("download_url") or DEFAULT_DRIVE_DOWNLOAD_URL,
        "changelog": latest_version_cache.get("release_notes", ""),
        "last_checked": latest_version_cache.get("checked_at", ""),
        "tag": latest_version_cache.get("tag", f"v{APP_VERSION}"),
    })



# ==================== WebSocket 即時串流 ====================

@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)

    # 立即向剛連線的前端推送當前報告資訊（若有快取直接呈現，避免等待輪詢）
    try:
        init_sheets_msg = json.dumps({
            "type": "sheets_report_update",
            **sheets_manager.get_payload(),
        })
        await websocket.send_text(init_sheets_msg)
    except Exception:
        pass

    # 若已有版本更新快取，立即推送版本狀態給前端
    if latest_version_cache:
        try:
            await websocket.send_text(json.dumps({
                "type": "version_update",
                "data": latest_version_cache,
            }))
        except Exception:
            pass

    try:
        while True:
            # 接收前端可能發送的心跳或控制訊號
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_websockets:
            active_websockets.remove(websocket)
    except Exception:
        if websocket in active_websockets:
            active_websockets.remove(websocket)


if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
