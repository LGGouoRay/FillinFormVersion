# FillinForm — 台科大四平台同儕互評統一填寫工具

> 依據 `build.md` 規範之安全、可手動介入、零幻覺同儕互評本機自動化輔助工具。

---

## 🌟 核心特性與設計架構

1. **真實可見、可手動介入之 Playwright 雙視窗**：
   - 捨棄 CSP/反向代理破壁風險，由本機 Playwright 引擎持久化託管 4 大平台（`./profile` 保留學生手動登入狀態）。
   - 後端每 500ms 透過 WebSocket 串流四分割畫面至毛玻璃儀表板。
   - 點擊任一分割畫面即可透過 `bring_to_front()` 將該站真實瀏覽器頁籤切換至最上層供手動檢查或修正。
2. **前後端雙一致分數換算引擎 (ScoreEngine)**：
   - 輸入五向度（主題 30%、內容 30%、敘事 20%、簡報 10%、團隊 10%）。
   - **S1 (ChatGPT 互評站)**：`clamp(round(x/20), 0, 5)` 五項 0~5 級分整數陣列。
   - **S2/S3 (Stanley Owen / Google 表單)**：`30 / 30 / 20 / 10 / 10` 個別 round & clamp，加權總分上限 100。
   - **S4 (NLA 平台)**：原值 clamp 至 `[0, 100]`，附 1 位小數加權總分。
   - 強防禦性數值清洗：拒絕 NaN / None / 非法字串 / 超邊界值。
3. **四大防呆保護機制 (Anti-Fooling)**：
   - **自我互評防呆**：選到評審本人學號時自動鎖定按鈕，禁止提交。
   - **組別越界防呆**：組別嚴格限制在 1 ~ 50 之內，自動聯動帶出所屬組別。
   - **受評名單防呆**：僅限名單內 29 位同學，拒絕未授權學號。
   - **S3 下拉比對防呆**：優先動態解析 Google 表單真實下拉選單，比對失敗時立刻中止送出，禁止模糊猜測。
4. **人類最終覆核視窗與預設 Dry-Run 演練模式**：
   - 「🪄 填寫預覽」：填入 4 站但不按下送出，截圖回傳。
   - 「🚀 送出」：彈出毛玻璃覆核清單，支援勾選排除特定平台，預設勾選 Dry-Run 演練。
5. **看板娘狀態機與評語卡池**：
   - SVG 動畫看板娘：`IDLE` / `INPUT` / `DRYRUN` / `LAUNCH` / `SUCCESS` / `WARNING`，具備眨眼與對話泡泡。
   - 純靜態卡池（SSR / SR / R / N 四級），無任何分數偽裝與隨機擾動。

---

## 📂 專案檔案結構

```
version3/Kimi3_prompt/
├── core/
│   ├── __init__.py
│   ├── score_engine.py      # 五向度換算與防禦清洗引擎
│   ├── students_data.py     # 29 位同學對照表與四大防呆邏輯
│   ├── chatgpt_client.py    # S1 ChatGPT 互評站 API 客戶端
│   ├── firebase_client.py   # S2 Stanley Owen Firebase/Firestore 客戶端
│   ├── googleform_client.py # S3 Google 表單動態解析與 POST 客戶端
│   ├── nla_client.py        # S4 NLA 平台 JWT 與評分客戶端
│   └── browser_manager.py   # Playwright 持久化控制器與 WebSocket 畫面串流
├── static/
│   ├── index.html           # 霓虹毛玻璃統一儀表板
│   ├── css/style.css        # #0A0B10, #FF75A0, #00F5D4, #7928CA 配色
│   └── js/
│       ├── score_engine.js  # 前端分數換算引擎 (與後端 100% 一致)
│       ├── mascot.js        # SVG 看板娘狀態機與動畫
│       ├── gacha.js         # 純靜態評語建議卡池
│       └── app.js           # 儀表板控制邏輯與 WebSocket 連線
├── evidence/
│   ├── session.har          # 第一階段 Playwright 逆向攔截真實 HAR (9.3 MB)
│   └── traffic_evidence.json# 四大平台真實請求/回應封包記錄
├── screenshots/             # 4 平台畫面與填寫截圖存證
├── profile/                 # Playwright 持久化瀏覽器 Context
├── verified_spec.md         # 第一階段逆向工程端點驗證報告
├── verify.py                # 自動化邊界、防呆與連線驗收測試腳本
├── server.py                # FastAPI 微伺服器 (僅綁定 127.0.0.1)
├── requirements.txt         # Python 依賴清單
├── credentials.example.json # 憑證範本檔
├── run.bat                  # Windows 一鍵啟動批次檔 (支援自動建置 venv)
├── run.sh                   # macOS / Linux 終端機啟動腳本
└── run.command              # macOS Finder 雙擊即開啟動腳本
```

---

## 🚀 啟動與使用方式

### 🍎 macOS 使用方式

#### 方式一：Finder 雙擊啟動（最簡單）
1. 在 Finder 中進入本專案資料夾。
2. 若首次執行，對 `run.command` 點右鍵選「打開」（或於終端機執行一次 `chmod +x run.sh run.command`）。
3. 之後**直接雙擊 `run.command`**，系統會自動開啟 Terminal、建立虛擬環境、下載 Chromium 並啟動儀表板！

#### 方式二：Terminal 終端機執行
```bash
# 賦予執行權限並啟動
chmod +x run.sh
./run.sh
```

---

### 🪟 Windows 使用方式

#### 方式一：雙擊執行腳本
直接雙擊 `run.bat`：
- 自動偵測已存在的 Python 3.14 `.venv`（若無則自動建立）。
- 自動補裝依賴與 Playwright Chromium 瀏覽器核心。
- 自動開啟儀表板 `http://127.0.0.1:8000` 並彈出 Playwright 瀏覽器視窗。

#### 方式二：手動終端機啟動
```powershell
# 啟動虛擬環境 (以 Windows 為例)
..\..\.venv\Scripts\activate

# 執行驗收測試 (全綠通過)
python verify.py

# 啟動主伺服器
python server.py
```

---

## 🧪 驗收測試項目 (Definition of Done)

執行 `python verify.py` 即可自動驗證：
1. **換算引擎邊界條件**：88 分換算（S1 級分 `[4,4,4,4,4]`、S2/S3 總分 `88`、S4 加權 `88.0`）、0 分極限、100 滿分、NaN/None/非法字串防禦性清洗全過。
2. **四大防呆情境**：自我互評阻擋、組別越界（<1 或 >50）、無效對象、S3 下拉比對失敗皆確實中斷。
3. **四大平台連線**：S1 學生查詢、S2 Firebase 認證、S3 名單解析、S4 JWT 與作業清單連線全數成功。
4. **S1 里程碑驗證**：查詢 -> 換算 -> 截圖證據全數就緒。
