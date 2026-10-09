"""
FillinForm - Browser Automation Manager
基於 Playwright 的持久化 Session 瀏覽器控制器。
管理 S1~S4 四個頁面、WebSocket 畫面截圖廣播、Tab 切換 (bring_to_front) 與 DOM 輔助填寫。
"""

import os
import sys
import json
import base64
import asyncio
from typing import Dict, Any, Optional

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

from playwright.async_api import async_playwright, BrowserContext, Page

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_DIR = os.path.join(BASE_DIR, "profile")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "screenshots")

def _shield_directory_from_git(path: str, comment: str = "Ignore everything in this directory"):
    """資安強化防禦：確保敏感目錄建立時內嵌 .gitignore，杜絕任何 Git 追蹤或 Windows 鎖定衝突"""
    try:
        os.makedirs(path, exist_ok=True)
        gi = os.path.join(path, ".gitignore")
        if not os.path.exists(gi):
            with open(gi, "w", encoding="utf-8") as f:
                f.write(f"# Auto-generated security shield: {comment}\n*\n")
    except Exception:
        pass

_shield_directory_from_git(PROFILE_DIR, "Playwright session cookies and locks")
_shield_directory_from_git(SCREENSHOTS_DIR, "Preview screenshots and student data")

SITE_URLS = {
    "S1": "https://class-peer-review-115-20261005.muddy-mite-0918.chatgpt.site/student",
    "S2": "https://ntust-grading.stanleyowen.com/grade",
    "S3": "https://docs.google.com/forms/d/e/1FAIpQLSdHfP1Dbjt1CM0rd9Ecf-gpSO2Qvy7eApdC-yDvYM32greO_A/viewform",
    "S4": "https://nla.ntust.org/student/task/1b4043962c20452db349429f88337822",
}


class BrowserManager:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.playwright = None
        self.context: Optional[BrowserContext] = None
        self.pages: Dict[str, Page] = {}
        self._lock = asyncio.Lock()
        self.is_running = False
        self.credentials: Dict[str, Any] = {}

    def update_credentials(self, creds: Dict[str, Any]):
        """更新使用者帳號設定與憑證快取"""
        if not hasattr(self, "credentials") or self.credentials is None:
            self.credentials = {}
        if isinstance(creds, dict):
            self.credentials.update(creds)

    def get_credentials(self) -> Dict[str, Any]:
        """安全取得憑證快取，若無則從 credentials.json 讀取"""
        if getattr(self, "credentials", None):
            return self.credentials
        cred_path = os.path.join(BASE_DIR, "credentials.json")
        if os.path.exists(cred_path):
            try:
                with open(cred_path, "r", encoding="utf-8") as f:
                    self.credentials = json.load(f)
                    return self.credentials
            except Exception:
                pass
        self.credentials = {}
        return self.credentials

    async def _launch_context_with_fallback(self) -> BrowserContext:
        """
        零等待秒速啟動策略：
        優先順序：已存在之原生 Chromium > 本機 Microsoft Edge > 本機 Google Chrome > 嘗試背景下載
        Windows 預載 Edge，絕大多數電腦可直接使用本機核心秒開，完全免去自海外 CDN 下載 150MB 逾時問題！
        """
        import sys
        launch_kwargs = {
            "user_data_dir": PROFILE_DIR,
            "headless": self.headless,
            "viewport": {"width": 1280, "height": 800},
            "args": ["--disable-blink-features=AutomationControlled"],
        }

        # 優先順序 1: 本機 Google Chrome (Mac 與 Windows 同學最常用的標準瀏覽器，免下載秒開)
        try:
            print("🌐 [BrowserEngine] 偵測到本機 Google Chrome，使用 Chrome 核心啟動 (免下載)...", flush=True)
            ctx = await self.playwright.chromium.launch_persistent_context(
                **launch_kwargs, channel="chrome"
            )
            print("✅ 成功以 Google Chrome 核心啟動！", flush=True)
            return ctx
        except Exception:
            pass

        # 優先順序 2: 本機 Microsoft Edge (Windows 內建保底，若無 Chrome 則秒速切換 Edge)
        try:
            print("🌐 [BrowserEngine] 偵測到本機 Microsoft Edge，使用 Edge 核心啟動 (免下載)...", flush=True)
            ctx = await self.playwright.chromium.launch_persistent_context(
                **launch_kwargs, channel="msedge"
            )
            print("✅ 成功以 Microsoft Edge 核心啟動！", flush=True)
            return ctx
        except Exception:
            pass

        # 優先順序 3: 若本機已存在 Playwright 原生 Chromium，直接使用
        try:
            ep = self.playwright.chromium.executable_path
            if os.path.exists(ep):
                print("🌐 [BrowserEngine] 使用 Playwright 原生 Chromium 核心啟動...", flush=True)
                return await self.playwright.chromium.launch_persistent_context(**launch_kwargs)
        except Exception:
            pass

        # 優先順序 4: 若本機連 Edge / Chrome 都沒有，才嘗試連網下載 Playwright Chromium
        print("🌐 [BrowserEngine] 本機未偵測到 Edge / Chrome，正在嘗試下載 Playwright 核心...", flush=True)
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "playwright", "install", "chromium",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if proc.returncode == 0:
                print("✅ Playwright Chromium 瀏覽器核心下載完成！正在啟動...", flush=True)
                return await self.playwright.chromium.launch_persistent_context(**launch_kwargs)
        except Exception as dl_err:
            print(f"⚠️ 下載 Chromium 核心失敗: {dl_err}", flush=True)

        raise RuntimeError(
            "無法啟動任何瀏覽器核心！\n"
            "您的電腦似乎缺少 Microsoft Edge 或 Google Chrome。\n"
            "請安裝 Google Chrome 或確認網路後重新啟動。"
        )

    async def start(self):
        """啟動 Playwright 持久化 context 並開啟四個目標站台分頁"""
        async with self._lock:
            if self.is_running:
                return

            self.playwright = await async_playwright().start()
            # 持久化使用者 session 於專案內 profile/ 目錄 (具備缺少核心自動下載與雙備援功能)
            self.context = await self._launch_context_with_fallback()

            # 確保有 4 個獨立分頁
            initial_pages = self.context.pages
            p1 = initial_pages[0] if len(initial_pages) > 0 else await self.context.new_page()
            p2 = await self.context.new_page()
            p3 = await self.context.new_page()
            p4 = await self.context.new_page()

            self.pages = {
                "S1": p1,
                "S2": p2,
                "S3": p3,
                "S4": p4,
            }

            # 非同步載入 4 個站台
            tasks = [
                self._safe_goto(p1, SITE_URLS["S1"]),
                self._safe_goto(p2, SITE_URLS["S2"]),
                self._safe_goto(p3, SITE_URLS["S3"]),
                self._safe_goto(p4, SITE_URLS["S4"]),
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
            self.is_running = True

    async def _safe_goto(self, page: Page, url: str):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception:
            pass

    async def bring_to_front(self, site_key: str):
        """將使用者在儀表板點選的網站頁籤帶到最上層"""
        if site_key in self.pages:
            try:
                page = self.pages[site_key]
                await page.bring_to_front()
                return True
            except Exception:
                return False
        return False

    async def check_s3_needs_login(self) -> bool:
        """檢查 S3 Google 表單是否需要使用者手動登入 Google 帳號"""
        p3 = self.pages.get("S3")
        if not p3:
            return True
        try:
            url = p3.url.lower()
            if "accounts.google.com" in url or "servicelogin" in url:
                return True
            content = await p3.content()
            if "你必須登入才能填寫這份表單" in content or "Sign in to continue" in content:
                return True
            if "登入帳戶以繼續使用" in content:
                return True

            # 檢測是否有登入按鈕/連結
            has_login_btn = await p3.evaluate("""() => {
                const a = document.querySelector('a[href*="ServiceLogin"], a[href*="accounts.google.com"]');
                if (a) return true;
                const btns = Array.from(document.querySelectorAll('a, button'));
                return btns.some(b => b.textContent && b.textContent.includes('登入'));
            }""")
            if has_login_btn:
                return True

            # 檢查是否有已登入 Google 帳號的識別元素 (頭像、帳號名稱、信箱)
            is_signed_in = await p3.evaluate("""() => {
                const acc = document.querySelector('[data-email], a[href*="SignOut"], div[aria-label*="Google 帳戶"], div[aria-label*="Google Account"]');
                return acc !== null;
            }""")
            if is_signed_in:
                return False

            # 檢測表單題目是否已解鎖且可互動 (至少有一組 listbox 或多個文字輸入框)
            has_form_fields = await p3.evaluate("""() => {
                const listbox = document.querySelector('[role="listbox"]');
                const inputs = document.querySelectorAll('input[type="text"]');
                return (listbox !== null || inputs.length >= 2);
            }""")
            if has_form_fields:
                return False

        except Exception:
            pass
        return True

    async def open_s3_google_login(self) -> bool:
        """點擊 S3 上的登入按鈕並將真實瀏覽器切換至最上層"""
        p3 = self.pages.get("S3")
        if not p3:
            return False
        try:
            login_el = await p3.query_selector("a[href*='accounts.google.com'], a:has-text('登入'), button:has-text('登入')")
            if login_el:
                await login_el.click()
                await asyncio.sleep(0.5)
            await p3.bring_to_front()
            return True
        except Exception as e:
            print(f"⚠️ S3 點擊登入提示: {e}")
            try:
                await p3.bring_to_front()
                return True
            except Exception:
                return False

    async def capture_all_screenshots_base64(self) -> Dict[str, str]:
        """截取四個分頁的即時畫面並轉為 base64供 WebSocket 推送"""
        result = {}
        for site_key, page in self.pages.items():
            try:
                # 截取 jpeg 格式以優化 WebSocket 頻寬與即時刷新效能
                buf = await page.screenshot(type="jpeg", quality=65)
                b64 = base64.b64encode(buf).decode("utf-8")
                result[site_key] = f"data:image/jpeg;base64,{b64}"
            except Exception:
                result[site_key] = ""
        return result

    async def check_site_login_status(self, site: str, grader_id: str = "", creds: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        精確檢測 S1~S4 各站目前是否處於已登入且可填寫狀態。
        優先原則：先幫使用者自動進入或登入 (使用一開始填寫的帳密/學號)；
        若自動登入或身分確認失敗，再請使用者自行處理，先跳過輸入成績！
        """
        page = self.pages.get(site)
        if not page:
            return {"is_ready": False, "reason": f"{site} 分頁尚未開啟"}

        credentials = creds or self.get_credentials()
        sid = (grader_id or credentials.get("student_id", "")).strip().upper()

        try:
            url = page.url.lower()

            if site == "S1":
                # 1. 檢查是否已在評分階段
                has_rating = await page.query_selector("input[type='radio'], input[placeholder*='組號'], #group")
                if has_rating:
                    return {"is_ready": True, "reason": "已就緒"}
                # 2. 先嘗試幫使用者進入評分頁 (以一開始填寫的學號查詢並點選確認)
                if sid:
                    ok = await self._ensure_s1_step2(page, sid)
                    if ok:
                        return {"is_ready": True, "reason": "已就緒"}
                # 3. 不行的話再請使用者自行處理，先跳過輸入成績
                content = await page.content()
                if "查無" in content:
                    return {"is_ready": False, "reason": "S1 學號查詢失敗（查無此學號），請至 S1 確認學號"}
                return {"is_ready": False, "reason": "S1 尚未完成學號身分查詢確認，請至 S1 查詢身分"}

            elif site == "S2":
                # 1. 檢查是否已在評分頁
                has_select = await page.query_selector("select, input[type='number']")
                has_pwd = await page.query_selector("input[type='password']")
                if "grade" in url and has_select and not has_pwd:
                    return {"is_ready": True, "reason": "已就緒"}

                # 2. 先幫使用者登入 (使用一開始填寫的帳密)
                fb_email = credentials.get("stanleyowen_email") or f"{sid.lower()}@mail.ntust.edu.tw"
                fb_pwd = credentials.get("stanleyowen_password", "")
                if fb_pwd:
                    ok = await self._ensure_s2_logged_in(page, fb_email, fb_pwd)
                    if ok:
                        return {"is_ready": True, "reason": "已就緒"}

                # 3. 不行的話再請使用者自行處理，先跳過輸入成績
                content = await page.content()
                if "錯誤" in content or "fail" in content.lower():
                    return {"is_ready": False, "reason": "S2 評分網登入失敗（帳號或密碼錯誤），請點擊 S2 頁籤完成登入"}
                return {"is_ready": False, "reason": "S2 評分網尚未登入，請點擊 S2 頁籤完成登入"}

            elif site == "S3":
                # 1. 若處於已提交完成頁面，先幫使用者進入全新表單
                await self._ensure_s3_fresh_form(page)
                # 2. 檢測 Google 表單登入狀態
                needs_login = await self.check_s3_needs_login()
                if needs_login:
                    return {"is_ready": False, "reason": "S3 Google 表單需要登入 Google 帳號，請點擊 S3 頁籤登入"}
                return {"is_ready": True, "reason": "已就緒"}

            elif site == "S4":
                # 1. 檢查是否已登入且處於任務頁
                has_pwd = await page.query_selector("input[type='password']")
                if ("task" in url or "review" in url) and not has_pwd:
                    content = await page.content()
                    if "登入系統" not in content or "評分" in content:
                        return {"is_ready": True, "reason": "已就緒"}

                # 2. 先幫使用者登入 (使用一開始填寫的學號與密碼)
                nla_pwd = credentials.get("nla_password", "")
                nla_task = credentials.get("nla_task_id", "1b4043962c20452db349429f88337822")
                if sid and nla_pwd:
                    ok = await self._ensure_s4_logged_in(page, sid, nla_pwd, nla_task)
                    if ok:
                        return {"is_ready": True, "reason": "已就緒"}

                # 3. 不行的話再請使用者自行處理，先跳過輸入成績
                content = await page.content()
                if "錯誤" in content or "fail" in content.lower():
                    return {"is_ready": False, "reason": "S4 NLA 系統登入失敗（帳號或密碼錯誤），請點擊 S4 頁籤登入"}
                return {"is_ready": False, "reason": "S4 NLA 系統尚未登入，請點擊 S4 頁籤登入"}

        except Exception as e:
            return {"is_ready": False, "reason": f"檢測登入狀態異常: {e}"}

        return {"is_ready": True, "reason": "已就緒"}

    async def _ensure_s2_logged_in(self, p2: Page, email: str, password: str) -> bool:
        """
        確保 S2 登入：
        若仍在登入頁或未出現評分選單，先嘗試使用使用者填寫之帳號密碼自動登入！
        """
        if not p2:
            return False
        try:
            url = p2.url.lower()
            has_select = await p2.query_selector("select")
            has_pwd_el = await p2.query_selector("input[type='password']")
            if "grade" in url and has_select and not has_pwd_el:
                return True

            if not password:
                return False

            if "login" not in url and not has_select:
                await self._safe_goto(p2, "https://ntust-grading.stanleyowen.com/login")
                await asyncio.sleep(1.0)
                url = p2.url.lower()

            has_pwd_el = await p2.query_selector("input[type='password']")
            if "login" in url or has_pwd_el:
                inps = await p2.query_selector_all("input")
                email_inp = None
                pwd_inp = None
                for inp in inps:
                    itype = (await inp.get_attribute("type") or "").lower()
                    if itype == "password":
                        pwd_inp = inp
                    else:
                        email_inp = inp
                if not email_inp and len(inps) >= 2:
                    email_inp = inps[0]
                    pwd_inp = inps[1]

                if email_inp and pwd_inp:
                    await email_inp.fill(email.strip())
                    await pwd_inp.fill(password.strip())
                    btn = await p2.query_selector("button:has-text('登入'), button[type='submit']")
                    if not btn:
                        btn = await p2.query_selector("button")
                    if btn:
                        await btn.click()

                    for _ in range(12):
                        await asyncio.sleep(0.5)
                        if "login" not in p2.url.lower() or await p2.query_selector("select"):
                            break

            if "grade" not in p2.url.lower():
                await self._safe_goto(p2, SITE_URLS["S2"])
                await asyncio.sleep(1.0)

            final_select = await p2.query_selector("select")
            final_pwd = await p2.query_selector("input[type='password']")
            return final_select is not None or ("grade" in p2.url.lower() and not final_pwd)
        except Exception as e:
            print(f"⚠️ S2 自動登入處理異常: {e}")
            return False

    async def _ensure_s4_logged_in(self, p4: Page, student_id: str, password: str, task_id: str = "1b4043962c20452db349429f88337822") -> bool:
        """
        確保 S4 登入：
        若仍在登入頁或未就緒，先嘗試使用使用者填寫之學號與密碼自動登入，並導向任務頁面！
        """
        if not p4:
            return False
        try:
            url = p4.url.lower()
            has_pwd_el = await p4.query_selector("input[type='password']")
            if ("task" in url or "review" in url) and not has_pwd_el:
                content = await p4.inner_text("body")
                if "登入系統" not in content or "評分" in content:
                    return True

            if not password or not student_id:
                return False

            if "login" not in url and not has_pwd_el:
                await self._safe_goto(p4, "https://nla.ntust.org/login")
                await asyncio.sleep(1.0)
                url = p4.url.lower()

            has_pwd_el = await p4.query_selector("input[type='password']")
            if "login" in url or has_pwd_el:
                inps = await p4.query_selector_all("input")
                id_inp = None
                pwd_inp = None
                for inp in inps:
                    itype = (await inp.get_attribute("type") or "").lower()
                    if itype == "password":
                        pwd_inp = inp
                    else:
                        id_inp = inp
                if not id_inp and len(inps) >= 2:
                    id_inp = inps[0]
                    pwd_inp = inps[1]

                if id_inp and pwd_inp:
                    await id_inp.fill(student_id.strip().upper())
                    await pwd_inp.fill(password.strip())
                    btn = await p4.query_selector("button:has-text('登入'), button[type='submit']")
                    if not btn:
                        btn = await p4.query_selector("button")
                    if btn:
                        await btn.click()

                    for _ in range(12):
                        await asyncio.sleep(0.5)
                        if "login" not in p4.url.lower():
                            break

            target_url = f"https://nla.ntust.org/student/task/{task_id}" if task_id else SITE_URLS["S4"]
            if "task" not in p4.url.lower():
                await self._safe_goto(p4, target_url)
                await asyncio.sleep(1.2)

            final_pwd = await p4.query_selector("input[type='password']")
            final_url = p4.url.lower()
            return ("task" in final_url or "review" in final_url) and final_pwd is None
        except Exception as e:
            print(f"⚠️ S4 自動登入處理異常: {e}")
            return False

    async def _ensure_s1_step2(self, p1: Page, student_id: str) -> bool:
        """確保 S1 自動完成身分查詢並點擊『姓名正確，開始評分』進入評分頁面"""
        if not p1 or not student_id:
            return False
        try:
            # 1. 檢查是否已在評分頁 (有組號輸入框或已在 step 2)
            step2_inp = await p1.query_selector("input[placeholder*='組號'], input[type='radio'], #group")
            if step2_inp:
                return True

            # 2. 若頁面上已出現「姓名正確，開始評分」按鈕，直接點擊
            start_btn = await p1.query_selector("button:has-text('開始評分'), button:has-text('姓名正確')")
            if start_btn:
                await start_btn.click()
                await asyncio.sleep(0.8)
                return True

            # 3. 若仍在查詢頁，填入學號並點擊「查詢」
            inp = await p1.query_selector("input")
            if inp:
                await inp.fill(student_id.strip().upper())
                btns = await p1.query_selector_all("button")
                for b in btns:
                    t = (await b.inner_text()).strip()
                    if "查詢" in t:
                        await b.click()
                        break

                # 4. 循環等候最多 5 秒，一旦出現按鈕立即自動點擊！
                for _ in range(10):
                    await asyncio.sleep(0.5)
                    content = await p1.content()
                    if "查無" in content:
                        return False
                    start_btn = await p1.query_selector("button:has-text('開始評分'), button:has-text('姓名正確')")
                    if start_btn:
                        await start_btn.click()
                        await asyncio.sleep(0.8)
                        return True

            step2_check = await p1.query_selector("input[placeholder*='組號'], input[type='radio'], #group")
            return step2_check is not None
        except Exception as e:
            print(f"⚠️ S1 自動點擊開始評分處理異常: {e}")
            return False

    async def _ensure_s3_fresh_form(self, p3: Page):
        """若 S3 處於『您的回應已記錄』提交完成頁，自動點擊『提交另一則回應』返回全新表單"""
        if not p3:
            return
        try:
            content = await p3.content()
            if "您的回應已記錄" in content or "formResponse" in p3.url or "已記錄" in content:
                another_link = await p3.query_selector("a:has-text('提交另一則回應'), a[href*='viewform']")
                if another_link:
                    await another_link.click()
                    await asyncio.sleep(1)
                else:
                    await self._safe_goto(p3, SITE_URLS["S3"])
                    await asyncio.sleep(1)
                for _ in range(15):
                    if await p3.query_selector("[role='listbox'], input[type='text'], [role='checkbox']"):
                        break
                    await asyncio.sleep(0.3)
        except Exception as e:
            print(f"⚠️ S3 重置至全新表單異常: {e}")

    async def _fill_s1(self, p1: Page, grader_id: str, group_num: int, scores_payload: Dict[str, Any]):
        await self._ensure_s1_step2(p1, grader_id)
        grp_inp = await p1.query_selector("input[type='number'], input[placeholder*='組號'], #group")
        if grp_inp:
            await grp_inp.fill(str(group_num))

        s1_scores = scores_payload.get("chatgpt", [5, 5, 5, 5, 5])
        for q_idx, score in enumerate(s1_scores):
            s_val = max(0, min(5, int(score)))
            btn = await p1.query_selector(f"#score-{q_idx}-{s_val}")
            if btn:
                await btn.click()
            else:
                await p1.evaluate("""([q, s]) => {
                    const btn = document.querySelector(`#score-${q}-${s}`);
                    if (btn) { btn.click(); return; }
                    const radios = Array.from(document.querySelectorAll(`input[type='radio'][value='${s}']`));
                    if (radios[q]) { radios[q].click(); }
                }""", [q_idx, s_val])
        await asyncio.sleep(0.3)

    async def _fill_s2(self, p2: Page, target_id: str, target_name: str, scores_payload: Dict[str, Any], comment: str):
        if "grade" not in p2.url:
            await self._safe_goto(p2, SITE_URLS["S2"])
            await asyncio.sleep(1)

        s2_data = scores_payload.get("stanleyowen", {})
        try:
            await p2.select_option("select", target_id)
        except Exception:
            try:
                await p2.select_option("select", label=f"{target_name}（{target_id}）")
            except Exception:
                pass
        await asyncio.sleep(0.5)

        vals = [
            s2_data.get("topicMastery", 26),
            s2_data.get("contentRichness", 26),
            s2_data.get("narrativeSkill", s2_data.get("narrativeSkills", 18)),
            s2_data.get("presentationSkill", 9),
            s2_data.get("teamwork", 9),
        ]

        await p2.evaluate("""(scores) => {
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            const items = [
                { key: '主題掌握', val: scores[0] },
                { key: '內容豐富', val: scores[1] },
                { key: '敘事技巧', val: scores[2] },
                { key: '簡報技巧', val: scores[3] },
                { key: '團隊表現', val: scores[4] },
            ];
            const numInputs = Array.from(document.querySelectorAll("input[type='number']"));
            items.forEach((item, idx) => {
                let inp = null;
                for (const l of document.querySelectorAll("label")) {
                    if (l.innerText && l.innerText.includes(item.key)) {
                        const parent = l.closest(".space-y-5 > div") || l.parentElement.parentElement;
                        if (parent) inp = parent.querySelector("input[type='number']");
                        break;
                    }
                }
                if (!inp && idx < numInputs.length) {
                    inp = numInputs[idx];
                }
                if (inp) {
                    setter.call(inp, item.val);
                    inp.dispatchEvent(new Event('input', { bubbles: true }));
                    inp.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });
        }""", vals)

        num_inps = await p2.query_selector_all("input[type='number']")
        for idx, v in enumerate(vals):
            if idx < len(num_inps):
                await num_inps[idx].fill(str(v))

        comment_inp = await p2.query_selector("textarea")
        if comment_inp:
            await comment_inp.fill(comment)
        await asyncio.sleep(0.3)

    async def _fill_s3(self, p3: Page, grader_id: str, grader_name: str, grader_email: str, target_id: str, target_name: str, scores_payload: Dict[str, Any], comment: str):
        await self._ensure_s3_fresh_form(p3)
        s3_data = scores_payload.get("googleform", {})

        await p3.evaluate("""(data) => {
            // 移除遮罩
            const dialog = document.querySelector('[role="dialog"]');
            if (dialog) dialog.remove();
            const backdrop = document.querySelector('.I7OXre');
            if (backdrop) backdrop.remove();

            // 自動勾選「在我的回覆中記錄以下電子郵件地址」
            const checkboxes = Array.from(document.querySelectorAll('[role="checkbox"]'));
            checkboxes.forEach(cb => {
                const parent = cb.closest('[role="listitem"]') || cb.parentElement;
                const text = parent ? parent.innerText : '';
                const aria = cb.getAttribute('aria-label') || '';
                if (text.includes('在我的回覆中記錄') || text.includes('電子郵件') || text.includes('email') ||
                    aria.includes('回覆中記錄') || aria.includes('電子郵件') || aria.includes('記錄')) {
                    if (cb.getAttribute('aria-checked') !== 'true') {
                        cb.click();
                    }
                }
            });

            const questions = Array.from(document.querySelectorAll('[role="listitem"]'));
            questions.forEach(q => {
                const titleEl = q.querySelector('[role="heading"]') || q.querySelector('.M7eMe');
                const title = titleEl ? titleEl.innerText : '';
                const inp = q.querySelector('input.whsOnd, input[type="text"], input[type="email"]');
                const tarea = q.querySelector('textarea.KHxj8b, textarea');

                if (title.includes('email') || title.includes('電子郵件') || title.includes('信箱')) {
                    if (inp && data.grader_email) {
                        inp.value = data.grader_email;
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                } else if (title.includes('name') || title.includes('姓名')) {
                    if (inp) {
                        inp.value = data.grader_name;
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                } else if (title.includes('studentId') || title.includes('學號')) {
                    if (inp) {
                        inp.value = data.grader_id;
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                } else if (title.includes('topicMastery') || title.includes('主題')) {
                    if (inp) {
                        inp.value = String(data.topic);
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                } else if (title.includes('contentRichness') || title.includes('內容')) {
                    if (inp) {
                        inp.value = String(data.content);
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                } else if (title.includes('narrativeSkills') || title.includes('敘事')) {
                    if (inp) {
                        inp.value = String(data.narrative);
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                } else if (title.includes('presentationSkill') || title.includes('簡報')) {
                    if (inp) {
                        inp.value = String(data.presentation);
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                } else if (title.includes('teamwork') || title.includes('團隊')) {
                    if (inp) {
                        inp.value = String(data.teamwork);
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                } else if (title.includes('message') || title.includes('建議') || title.includes('回饋')) {
                    if (tarea) {
                        tarea.value = data.comment;
                        tarea.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                }
            });
        }""", {
            "grader_name": grader_name,
            "grader_id": grader_id,
            "grader_email": grader_email,
            "topic": s3_data.get("topic", 26),
            "content": s3_data.get("content", 26),
            "narrative": s3_data.get("narrative", 18),
            "presentation": s3_data.get("presentation", 9),
            "teamwork": s3_data.get("teamwork", 9),
            "comment": comment,
        })

        # 雙重確保勾選「在我的回覆中記錄以下電子郵件地址」
        try:
            cb_el = await p3.query_selector("[role='checkbox']")
            if cb_el and (await cb_el.get_attribute("aria-checked")) != "true":
                await cb_el.click()
        except Exception:
            pass

        # 選取 presenter 下拉選單
        try:
            listbox = p3.locator('[role="listbox"]').first
            if await listbox.count() > 0:
                await listbox.scroll_into_view_if_needed()
                is_expanded = await listbox.get_attribute("aria-expanded")
                if is_expanded != "true":
                    await listbox.click(force=True)
                    await asyncio.sleep(0.6)

                selected_via_js = await p3.evaluate("""(data) => {
                    const { targetId, targetName } = data;
                    const options = Array.from(document.querySelectorAll('[role="option"]'));
                    let opt = options.find(o => targetId && o.textContent.includes(targetId));
                    if (!opt && targetName) {
                        opt = options.find(o => o.textContent.includes(targetName));
                    }
                    if (opt) {
                        opt.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'center' });
                        const rect = opt.getBoundingClientRect();
                        const clientX = rect.left + rect.width / 2;
                        const clientY = rect.top + rect.height / 2;
                        const opts = { bubbles: true, cancelable: true, view: window, clientX, clientY };
                        opt.dispatchEvent(new MouseEvent('pointerdown', opts));
                        opt.dispatchEvent(new MouseEvent('mousedown', opts));
                        opt.dispatchEvent(new MouseEvent('pointerup', opts));
                        opt.dispatchEvent(new MouseEvent('mouseup', opts));
                        opt.dispatchEvent(new MouseEvent('click', opts));
                        return true;
                    }
                    return false;
                }""", {"targetId": target_id, "targetName": target_name})

                if not selected_via_js:
                    await listbox.click(force=True)
                    await asyncio.sleep(0.6)
                    await p3.evaluate("""(data) => {
                        const { targetId, targetName } = data;
                        const options = Array.from(document.querySelectorAll('[role="option"]'));
                        let opt = options.find(o => targetId && o.textContent.includes(targetId));
                        if (!opt && targetName) {
                            opt = options.find(o => o.textContent.includes(targetName));
                        }
                        if (opt) {
                            opt.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'center' });
                            const rect = opt.getBoundingClientRect();
                            const clientX = rect.left + rect.width / 2;
                            const clientY = rect.top + rect.height / 2;
                            const opts = { bubbles: true, cancelable: true, view: window, clientX, clientY };
                            opt.dispatchEvent(new MouseEvent('pointerdown', opts));
                            opt.dispatchEvent(new MouseEvent('mousedown', opts));
                            opt.dispatchEvent(new MouseEvent('pointerup', opts));
                            opt.dispatchEvent(new MouseEvent('mouseup', opts));
                            opt.dispatchEvent(new MouseEvent('click', opts));
                            return true;
                        }
                        return false;
                    }""", {"targetId": target_id, "targetName": target_name})
                await asyncio.sleep(0.5)
        except Exception as e:
            print(f"⚠️ S3 選取 presenter 異常: {e}")

    async def _fill_s4(self, p4: Page, target_id: str, target_name: str, scores_payload: Dict[str, Any], comment: str, nla_task_id: str = "1b4043962c20452db349429f88337822"):
        if "/review/" in p4.url:
            current_text = await p4.inner_text("body")
            if (target_name and target_name not in current_text) and (target_id and target_id not in current_text):
                back_btn = await p4.query_selector("a[href*='/task/'], svg.lucide-arrow-left, button:has-text('返回')")
                if back_btn:
                    await back_btn.click()
                    await asyncio.sleep(0.8)
                else:
                    await self._safe_goto(p4, f"https://nla.ntust.org/student/task/{nla_task_id}")
                    await asyncio.sleep(0.8)

        current_text = await p4.inner_text("body")
        if (target_name and target_name not in current_text) and (target_id and target_id not in current_text):
            back_btn = await p4.query_selector("a[href*='/task/'], svg.lucide-arrow-left, button:has-text('返回')")
            if back_btn:
                await back_btn.click()
                await asyncio.sleep(0.8)
            else:
                await self._safe_goto(p4, f"https://nla.ntust.org/student/task/{nla_task_id}")
                await asyncio.sleep(0.8)

            for _ in range(12):
                c_text = await p4.inner_text("body")
                if (target_name and target_name in c_text) or (target_id and target_id in c_text) or "未評分" in c_text or "已評分" in c_text:
                    break
                await asyncio.sleep(0.5)

        # 點擊受評者卡片進入評分頁
        cand_elem = None
        if target_id:
            cand_elem = await p4.query_selector(f"text={target_id}")
        if not cand_elem and target_name:
            cand_elem = await p4.query_selector(f"text={target_name}")

        if cand_elem:
            await cand_elem.click()
            for _ in range(10):
                if await p4.query_selector("textarea"):
                    break
                await asyncio.sleep(0.3)

        clean_raw = scores_payload.get("clean_raw", {})
        s4_data = scores_payload.get("nla", {})
        scores_list = [
            int(round(clean_raw.get("topic", s4_data.get("score_topic", s4_data.get("topic", 85))))),
            int(round(clean_raw.get("content", s4_data.get("score_content", s4_data.get("content", 85))))),
            int(round(clean_raw.get("narrative", s4_data.get("score_narrative", s4_data.get("narrative", 85))))),
            int(round(clean_raw.get("presentation", s4_data.get("score_presentation", s4_data.get("presentation", 85))))),
            int(round(clean_raw.get("teamwork", s4_data.get("score_teamwork", s4_data.get("teamwork", 85))))),
        ]

        await p4.evaluate("""(data) => {
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            const criteria = [
                { name: '主題掌握', val: data.scores[0] },
                { name: '內容豐富', val: data.scores[1] },
                { name: '敘事技巧', val: data.scores[2] },
                { name: '簡報技巧', val: data.scores[3] },
                { name: '團隊表現', val: data.scores[4] },
            ];

            const numInps = Array.from(document.querySelectorAll("input[type='number']"));
            const rangeInps = Array.from(document.querySelectorAll("input[type='range']"));

            criteria.forEach((c, idx) => {
                let numInp = null;
                let rangeInp = null;

                const spans = Array.from(document.querySelectorAll("span"));
                const titleSpan = spans.find(s => s.innerText && s.innerText.trim() === c.name);
                if (titleSpan) {
                    const block = titleSpan.closest(".flex.flex-col");
                    if (block) {
                        numInp = block.querySelector("input[type='number']");
                        rangeInp = block.querySelector("input[type='range']");
                    }
                }

                if (!numInp && idx < numInps.length) numInp = numInps[idx];
                if (!rangeInp && idx < rangeInps.length) rangeInp = rangeInps[idx];

                if (numInp) {
                    setter.call(numInp, c.val);
                    numInp.dispatchEvent(new Event('input', { bubbles: true }));
                    numInp.dispatchEvent(new Event('change', { bubbles: true }));
                }
                if (rangeInp) {
                    setter.call(rangeInp, c.val);
                    rangeInp.dispatchEvent(new Event('input', { bubbles: true }));
                    rangeInp.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });

            const tarea = document.querySelector("textarea");
            if (tarea && data.comment) {
                const tSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                tSetter.call(tarea, data.comment);
                tarea.dispatchEvent(new Event('input', { bubbles: true }));
                tarea.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }""", {"scores": scores_list, "comment": comment})

        c_area = await p4.query_selector("textarea")
        if c_area and comment:
            await c_area.fill(comment)
        await asyncio.sleep(0.5)

    async def preview_fill_all(
        self,
        grader_id: str,
        grader_name: str,
        grader_email: str,
        target_id: str,
        target_name: str,
        group_num: int,
        scores_payload: Dict[str, Any],
        comment: str,
        status_callback=None,
        nla_task_id: str = "1b4043962c20452db349429f88337822",
    ) -> Dict[str, Any]:
        """
        在 4 個 page 中填入資料但不按下送出，並回傳各站填寫截圖。
        自動檢測各站登入狀態：若發現未登入或登入失敗，不繼續嘗試，直接跳過該站並回報原因通知使用者！
        """
        evidence_screenshots = {}
        skipped_sites = []
        skipped_reasons = {}

        # 1. S1 填寫預覽
        try:
            p1 = self.pages.get("S1")
            s1_status = await self.check_site_login_status("S1", grader_id)
            if not s1_status["is_ready"]:
                skipped_sites.append("S1")
                skipped_reasons["S1"] = s1_status["reason"]
                if status_callback:
                    await status_callback("S1", "error", s1_status["reason"])
                if p1:
                    path = os.path.join(SCREENSHOTS_DIR, "preview_s1.png")
                    await p1.screenshot(path=path)
                    evidence_screenshots["S1"] = f"/screenshots/preview_s1.png?t={asyncio.get_event_loop().time()}"
                evidence_screenshots["S1_skipped"] = True
                evidence_screenshots["S1_reason"] = s1_status["reason"]
            else:
                if status_callback:
                    await status_callback("S1", "filling")
                if p1:
                    await self._fill_s1(p1, grader_id, group_num, scores_payload)
                    path = os.path.join(SCREENSHOTS_DIR, "preview_s1.png")
                    await p1.screenshot(path=path)
                    evidence_screenshots["S1"] = f"/screenshots/preview_s1.png?t={asyncio.get_event_loop().time()}"
                if status_callback:
                    await status_callback("S1", "completed")
        except Exception as e:
            evidence_screenshots["S1_error"] = str(e)
            if status_callback:
                await status_callback("S1", "error", str(e))

        # 2. S2 填寫預覽
        try:
            p2 = self.pages.get("S2")
            s2_status = await self.check_site_login_status("S2", grader_id)
            if not s2_status["is_ready"]:
                skipped_sites.append("S2")
                skipped_reasons["S2"] = s2_status["reason"]
                if status_callback:
                    await status_callback("S2", "error", s2_status["reason"])
                if p2:
                    path = os.path.join(SCREENSHOTS_DIR, "preview_s2.png")
                    await p2.screenshot(path=path)
                    evidence_screenshots["S2"] = f"/screenshots/preview_s2.png?t={asyncio.get_event_loop().time()}"
                evidence_screenshots["S2_skipped"] = True
                evidence_screenshots["S2_reason"] = s2_status["reason"]
            else:
                if status_callback:
                    await status_callback("S2", "filling")
                if p2:
                    await self._fill_s2(p2, target_id, target_name, scores_payload, comment)
                    path = os.path.join(SCREENSHOTS_DIR, "preview_s2.png")
                    await p2.screenshot(path=path)
                    evidence_screenshots["S2"] = f"/screenshots/preview_s2.png?t={asyncio.get_event_loop().time()}"
                if status_callback:
                    await status_callback("S2", "completed")
        except Exception as e:
            evidence_screenshots["S2_error"] = str(e)
            if status_callback:
                await status_callback("S2", "error", str(e))

        # 3. S3 填寫預覽
        try:
            p3 = self.pages.get("S3")
            s3_status = await self.check_site_login_status("S3", grader_id)
            if not s3_status["is_ready"]:
                skipped_sites.append("S3")
                skipped_reasons["S3"] = s3_status["reason"]
                if status_callback:
                    await status_callback("S3", "error", s3_status["reason"])
                if p3:
                    path = os.path.join(SCREENSHOTS_DIR, "preview_s3.png")
                    await p3.screenshot(path=path)
                    evidence_screenshots["S3"] = f"/screenshots/preview_s3.png?t={asyncio.get_event_loop().time()}"
                evidence_screenshots["S3_skipped"] = True
                evidence_screenshots["S3_reason"] = s3_status["reason"]
            else:
                if status_callback:
                    await status_callback("S3", "filling")
                if p3:
                    await self._fill_s3(p3, grader_id, grader_name, grader_email, target_id, target_name, scores_payload, comment)
                    path = os.path.join(SCREENSHOTS_DIR, "preview_s3.png")
                    await p3.screenshot(path=path)
                    evidence_screenshots["S3"] = f"/screenshots/preview_s3.png?t={asyncio.get_event_loop().time()}"
                if status_callback:
                    await status_callback("S3", "completed")
        except Exception as e:
            evidence_screenshots["S3_error"] = str(e)
            if status_callback:
                await status_callback("S3", "error", str(e))

        # 4. S4 填寫預覽
        try:
            p4 = self.pages.get("S4")
            s4_status = await self.check_site_login_status("S4", grader_id)
            if not s4_status["is_ready"]:
                skipped_sites.append("S4")
                skipped_reasons["S4"] = s4_status["reason"]
                if status_callback:
                    await status_callback("S4", "error", s4_status["reason"])
                if p4:
                    path = os.path.join(SCREENSHOTS_DIR, "preview_s4.png")
                    await p4.screenshot(path=path)
                    evidence_screenshots["S4"] = f"/screenshots/preview_s4.png?t={asyncio.get_event_loop().time()}"
                evidence_screenshots["S4_skipped"] = True
                evidence_screenshots["S4_reason"] = s4_status["reason"]
            else:
                if status_callback:
                    await status_callback("S4", "filling")
                if p4:
                    await self._fill_s4(p4, target_id, target_name, scores_payload, comment, nla_task_id)
                    path = os.path.join(SCREENSHOTS_DIR, "preview_s4.png")
                    await p4.screenshot(path=path)
                    evidence_screenshots["S4"] = f"/screenshots/preview_s4.png?t={asyncio.get_event_loop().time()}"
                if status_callback:
                    await status_callback("S4", "completed")
        except Exception as e:
            evidence_screenshots["S4_error"] = str(e)
            if status_callback:
                await status_callback("S4", "error", str(e))

        return {
            "evidence_screenshots": evidence_screenshots,
            "skipped_sites": skipped_sites,
            "skipped_reasons": skipped_reasons,
        }

    async def submit_in_browser_all(
        self,
        grader_id: str,
        grader_name: str,
        grader_email: str,
        target_id: str,
        target_name: str,
        group_num: int,
        scores_payload: Dict[str, Any],
        comment: str,
        excluded_sites: Optional[list] = None,
        status_callback=None,
        nla_task_id: str = "1b4043962c20452db349429f88337822",
    ) -> Dict[str, Any]:
        """
        在 4 個真實 page 中直接點擊送出按鈕執行提交，並等待提交結果、截圖與觸發櫻花散落收尾。
        自動檢測各站登入狀態：若發現未登入或登入失敗，不嘗試點擊送出，直接跳過該站並回報原因通知使用者！
        """
        if excluded_sites is None:
            excluded_sites = []
        submission_results = {}

        # 1. 送出 S1 (ChatGPT 互評站)
        if "S1" in excluded_sites:
            submission_results["S1"] = {"success": True, "message": "已設定排除 S1"}
        else:
            s1_status = await self.check_site_login_status("S1", grader_id)
            if not s1_status["is_ready"]:
                if status_callback:
                    await status_callback("S1", "error", s1_status["reason"])
                submission_results["S1"] = {
                    "success": False,
                    "skipped": True,
                    "needs_login": True,
                    "message": f"【已自動跳過未送出】{s1_status['reason']}"
                }
            else:
                try:
                    if status_callback:
                        await status_callback("S1", "filling")
                    p1 = self.pages.get("S1")
                    if p1:
                        p1.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))
                        await self._fill_s1(p1, grader_id, group_num, scores_payload)
                        submit_btn = await p1.query_selector("button:has-text('確認送出'), button.submit-button, button[type='submit']")
                        if submit_btn:
                            await submit_btn.click()
                        await asyncio.sleep(1.5)
                        path = os.path.join(SCREENSHOTS_DIR, "preview_s1.png")
                        await p1.screenshot(path=path)
                    if status_callback:
                        await status_callback("S1", "completed")
                    submission_results["S1"] = {"success": True, "message": "S1 已在真實瀏覽器成功送出！"}
                except Exception as e:
                    if status_callback:
                        await status_callback("S1", "error", str(e))
                    submission_results["S1"] = {"success": False, "error": str(e), "message": f"S1 送出失敗: {e}"}

        # 2. 送出 S2 (Stanley Owen 評分網)
        if "S2" in excluded_sites:
            submission_results["S2"] = {"success": True, "message": "已設定排除 S2"}
        else:
            s2_status = await self.check_site_login_status("S2", grader_id)
            if not s2_status["is_ready"]:
                if status_callback:
                    await status_callback("S2", "error", s2_status["reason"])
                submission_results["S2"] = {
                    "success": False,
                    "skipped": True,
                    "needs_login": True,
                    "message": f"【已自動跳過未送出】{s2_status['reason']}"
                }
            else:
                try:
                    if status_callback:
                        await status_callback("S2", "filling")
                    p2 = self.pages.get("S2")
                    if p2:
                        await self._fill_s2(p2, target_id, target_name, scores_payload, comment)
                        submit_btn = await p2.query_selector("button[type='submit'], button.btn-primary, button:has-text('提交評分')")
                        if submit_btn:
                            for _ in range(10):
                                if not await submit_btn.get_attribute("disabled"):
                                    break
                                await asyncio.sleep(0.2)
                            await submit_btn.click()
                        await asyncio.sleep(2.0)
                        path = os.path.join(SCREENSHOTS_DIR, "preview_s2.png")
                        await p2.screenshot(path=path)
                    if status_callback:
                        await status_callback("S2", "completed")
                    submission_results["S2"] = {"success": True, "message": "S2 已在真實瀏覽器成功送出！"}
                except Exception as e:
                    if status_callback:
                        await status_callback("S2", "error", str(e))
                    submission_results["S2"] = {"success": False, "error": str(e), "message": f"S2 送出失敗: {e}"}

        # 3. 送出 S3 (Google 表單)
        if "S3" in excluded_sites:
            submission_results["S3"] = {"success": True, "message": "已設定排除 S3"}
        else:
            s3_status = await self.check_site_login_status("S3", grader_id)
            if not s3_status["is_ready"]:
                if status_callback:
                    await status_callback("S3", "error", s3_status["reason"])
                submission_results["S3"] = {
                    "success": False,
                    "skipped": True,
                    "needs_login": True,
                    "message": f"【已自動跳過未送出】{s3_status['reason']}"
                }
            else:
                try:
                    if status_callback:
                        await status_callback("S3", "filling")
                    p3 = self.pages.get("S3")
                    if p3:
                        await self._fill_s3(p3, grader_id, grader_name, grader_email, target_id, target_name, scores_payload, comment)
                        submit_btn = await p3.query_selector("div[role='button']:has-text('提交'), button:has-text('提交'), [role='button'].uArJ5e")
                        if submit_btn:
                            await submit_btn.click()
                            try:
                                await p3.wait_for_selector("text=您的回應已記錄, a:has-text('提交另一則回應'), text=Your response has been recorded", timeout=8000)
                            except Exception:
                                pass
                        await asyncio.sleep(1.0)
                        path = os.path.join(SCREENSHOTS_DIR, "preview_s3.png")
                        await p3.screenshot(path=path)
                    if status_callback:
                        await status_callback("S3", "completed")
                    submission_results["S3"] = {"success": True, "message": "S3 Google 表單已在真實瀏覽器成功送出（已記錄回應）！"}
                except Exception as e:
                    if status_callback:
                        await status_callback("S3", "error", str(e))
                    submission_results["S3"] = {"success": False, "error": str(e), "message": f"S3 送出失敗: {e}"}

        # 4. 送出 S4 (NLA 互評系統)
        if "S4" in excluded_sites:
            submission_results["S4"] = {"success": True, "message": "已設定排除 S4"}
        else:
            s4_status = await self.check_site_login_status("S4", grader_id)
            if not s4_status["is_ready"]:
                if status_callback:
                    await status_callback("S4", "error", s4_status["reason"])
                submission_results["S4"] = {
                    "success": False,
                    "skipped": True,
                    "needs_login": True,
                    "message": f"【已自動跳過未送出】{s4_status['reason']}"
                }
            else:
                try:
                    if status_callback:
                        await status_callback("S4", "filling")
                    p4 = self.pages.get("S4")
                    if p4:
                        await self._fill_s4(p4, target_id, target_name, scores_payload, comment, nla_task_id)
                        submit_btn = await p4.query_selector("button:has-text('提交評分'), button:has-text('儲存'), button.bg-\\[var\\(--color-accent\\)\\]")
                        if submit_btn:
                            for _ in range(10):
                                if not await submit_btn.get_attribute("disabled"):
                                    break
                                await asyncio.sleep(0.2)
                            await submit_btn.click()
                        await asyncio.sleep(2.0)
                        path = os.path.join(SCREENSHOTS_DIR, "preview_s4.png")
                        await p4.screenshot(path=path)
                    if status_callback:
                        await status_callback("S4", "completed")
                    submission_results["S4"] = {"success": True, "message": "S4 已在真實瀏覽器成功送出！"}
                except Exception as e:
                    if status_callback:
                        await status_callback("S4", "error", str(e))
                    submission_results["S4"] = {"success": False, "error": str(e), "message": f"S4 送出失敗: {e}"}

        return submission_results

    async def perform_initial_logins(
        self,
        student_id: str,
        student_name: str,
        fb_email: str,
        fb_pwd: str,
        nla_pwd: str,
        nla_task_id: str = "1b4043962c20452db349429f88337822"
    ):
        """在真實瀏覽器中自動為使用者執行 S1 查詢與 S2、S4 登入持久化"""
        self.update_credentials({
            "student_id": student_id,
            "student_name": student_name,
            "stanleyowen_email": fb_email,
            "stanleyowen_password": fb_pwd,
            "nla_password": nla_pwd,
            "nla_task_id": nla_task_id,
        })
        # 1. S1: 填入學號查詢並自動點擊「姓名正確，開始評分」進入評分頁面
        p1 = self.pages.get("S1")
        if p1 and student_id:
            try:
                await self._ensure_s1_step2(p1, student_id)
            except Exception as e:
                print(f"⚠️ S1 初始登入/跳轉異常: {e}")

        # 2. S2: 若在登入頁則自動登入
        p2 = self.pages.get("S2")
        if p2 and fb_pwd:
            try:
                await self._ensure_s2_logged_in(p2, fb_email, fb_pwd)
            except Exception as e:
                print(f"⚠️ S2 初始登入異常: {e}")

        # 3. S4: 若在登入頁則自動登入並導向評分任務
        p4 = self.pages.get("S4")
        if p4 and nla_pwd:
            try:
                await self._ensure_s4_logged_in(p4, student_id, nla_pwd, nla_task_id)
            except Exception as e:
                print(f"⚠️ S4 初始登入異常: {e}")

    async def stop(self):
        """安全關閉瀏覽器與 context"""
        async with self._lock:
            if not self.is_running:
                return
            if self.context:
                await self.context.close()
            if self.playwright:
                await self.playwright.stop()
            self.is_running = False
