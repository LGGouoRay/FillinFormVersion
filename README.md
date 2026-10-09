# 🌸 FillinForm — 台科大四平台同儕互評統一填寫工具
### *NTUST Peer Review Synchronizer & Automation Suite*

<p align="center">
  <img src="https://img.shields.io/badge/Version-3.51.1-FF75A0?style=for-the-badge&logo=git&logoColor=white" alt="Version 3.51.1">
  <img src="https://img.shields.io/badge/Python-3.10%20~%203.14-00F5D4?style=for-the-badge&logo=python&logoColor=black" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Engine-Playwright%20Headed-7928CA?style=for-the-badge&logo=playwright&logoColor=white" alt="Playwright">
  <img src="https://img.shields.io/badge/UI-Cyberpunk%20Glassmorphism-0A0B10?style=for-the-badge" alt="Neon Glassmorphism">
  <img src="https://img.shields.io/badge/Mascot-Interactive%20SVG-FF8FC4?style=for-the-badge" alt="Interactive Mascot">
  <img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="MIT License">
</p>

---

## 📖 專案目錄 (Table of Contents)
- [💡 緣起與痛點 (The Motivation)](#-緣起與痛點-the-motivation)
- [✨ 核心亮點與特色 (Superpowers)](#-核心亮點與特色-superpowers)
- [📊 四大互評平台規格矩陣 (Platform Matrix)](#-四大互評平台規格矩陣-platform-matrix)
- [📐 跨平台分數換算數學引擎 (ScoreEngine)](#-跨平台分數換算數學引擎-scoreengine)
- [🏛️ 系統架構與運作流程 (System Architecture)](#️-系統架構與運作流程-system-architecture)
- [🎮 視覺特效與趣味機制 (Visual & Easter Eggs)](#-視覺特效與趣味機制-visual--easter-eggs)
- [🚀 快速啟動指南 (Quick Start)](#-快速啟動指南-quick-start)
- [📁 專案檔案結構 (Project Structure)](#-專案檔案結構-project-structure)
- [🛡️ 資安、防呆與隱私承諾 (Security & Anti-Fooling)](#️-資安防呆與隱私承諾-security--anti-fooling)
- [🛠️ 常見問題與排解 (FAQ)](#️-常見問題與排解-faq)

---

## 💡 緣起與痛點 (The Motivation)

> **「同學請聽簡報，然後同時在 ChatGPT 站打 0~5 級分、Stanley 評分網填五項權重、Google 表單下拉選單找人填 100 分制、再去 NLA 平台拖拉滑桿評分……」**  
> ── *每週簡報課台科大學生的靈魂哀號*

每當課堂上報告者切換投影片，底下的評審同學必須在不到 3 分鐘內開啟 4 個不同網站、計算不同比例尺的加權總分、在動輒 30 人的下拉選單中肉眼搜尋學號，還要絞盡腦汁寫出不同回饋。一旦算錯分數或填錯平台，整組成績就陷入混亂。

**FillinForm** 應運而生！這是一套基於 **FastAPI + Playwright 持久化 Context + 賽博龐克毛玻璃儀表板** 的自動化輔助工具，只需拉動一組五向度滑桿，四個平台即時同步換算、預覽填寫並一鍵送出！

---

## ✨ 核心亮點與特色 (Superpowers)

### 🖥️ 1. 真實可見、可隨時介入的 Playwright 雙視窗
* **拒絕盲盒黑箱**：堅持以 Headed 原生視窗模式啟動，保留真實 Session。
* **零破壁、防封鎖**：不採有跨域與 CSP 風險的反向代理，透過持久化 `./profile` 儲存登入憑證。
* **WebSocket 4 分割即時畫面**：每 $500\text{ ms}$ 將四大站台最新畫面串流至儀表板，點擊任一分割視窗即可將該網頁 `bring_to_front()` 置頂操作。

### ⚙️ 2. 前後端雙一致分數換算引擎 (ScoreEngine)
* 前端 JavaScript 與後端 Python 邏輯 100% 鏡像對齊。
* 具備嚴格防禦性清洗：拒絕 $\text{NaN}$、$\text{None}$、越界值，強制收斂至 $[1, 100]$ 分間（不允許 $0$ 分極限故障）。

### 🛡️ 3. 堅不可摧的四大防呆保護機制 (Anti-Fooling)
1. **組別越界防呆**：嚴格鎖定於 $1 \sim 50$ 組，非整數或違規範圍即時攔截。
2. **29 位名冊嚴格比對**：內建名單校驗，杜絕填錯受評對象。
3. **S3 下拉選單動態解析**：即時抓取 Google 表單原始選項，比對失敗立即中斷，禁止模糊猜測送出。
4. **可選自我互評防呆**：評審本人與受評對象相同時彈出警示，防止誤扣自組分數。

### 🌸 4. 儀表板看板娘與櫻花流光物理引擎
* **動態 SVG 看板娘**：支援眨眼、情緒切換與動態台詞狀態機（`IDLE` / `INPUT` / `DRYRUN` / `LAUNCH` / `SUCCESS` / `WARNING`）。
* **雙光球環繞與櫻花飄落 (Sakura Petals Engine)**：填寫時粉色雙光球沿邊框高速環繞，並依物理阻尼演算法噴灑自然旋轉飄落的櫻花花瓣；完成提交時觸發收尾散落效果！

### 🔄 5. 熱更新守護程序 Supervisor (Exit Code 42)
* 透過 `launcher.py` 守護行程監控 `server.py`。
* 網頁端發動更新後，伺服器釋放資源並退出 Code 42，啟動器在完全備份後下載 GitHub Release 解壓熱更新，並自動無縫重啟，完整保護 `credentials.json` 與瀏覽器 Cookie。

---

## 📊 四大互評平台規格矩陣 (Platform Matrix)

| 平台代號 | 站台名稱 | 評分量尺 / 規則 | 特殊欄位與機制 | 提交模式 |
| :---: | :--- | :--- | :--- | :--- |
| **S1** | **ChatGPT 互評站** | $0 \sim 5$ 級分整數陣列 | 學號查詢身分確認、手動輸入組號 ($1 \sim 50$) | Playwright 點擊單選按鈕 / REST API |
| **S2** | **Stanley Owen 評分網** | 五向度加權整數分 ($30/30/20/10/10$)，總分上限 $100$ | Firebase Auth 登入、Firestore 讀寫、下拉選單選擇同學 | DOM 表單模擬注入 / Firestore REST API |
| **S3** | **Google 表單** | 各向度原始整數分 ($30/30/20/10/10$) | 動態解析 `entry.*`、強制勾選信箱記錄、下拉選單名冊匹配 | Playwright 下拉選單選取 / POST `formResponse` |
| **S4** | **NLA 互評平台** | $0 \sim 100$ 滑桿原值、加權總分 (保留 1 位小數) | JWT Bearer 認證、Assignment ID 查找、評語回饋文字框 | DOM 滑桿注入 / REST API `/api/assignments/submit` |

---

## 📐 跨平台分數換算數學引擎 (ScoreEngine)

使用者於儀表板輸入五向度基礎分數（範圍 $[1, 100]$）：
- $T$：主題掌握 (Topic Mastery, 權重 $30\%$)
- $C$：內容豐富 (Content Richness, 權重 $30\%$)
- $N$：敘事技巧 (Narrative Skill, 權重 $20\%$)
- $P$：簡報技巧 (Presentation Skill, 權重 $10\%$)
- $W$：團隊表現 (Teamwork, 權重 $10\%$)

### 換算公式

1. **加權總分 (Weighted Total)**：
   $$\text{Total} = \text{round}\Big(0.30T + 0.30C + 0.20N + 0.10P + 0.10W,\ 1\Big)$$

2. **S1 (ChatGPT 互評站 0~5 級分)**：
   $$S1_x = \text{clamp}\left(\text{round}\left(\frac{x}{20}\right),\ 0,\ 5\right), \quad \forall x \in \{T, C, N, P, W\}$$

3. **S2 & S3 (Stanley Owen / Google 表單權重制)**：
   $$\begin{aligned}
   \text{Topic} &= \text{clamp}(\text{round}(0.30T),\ 0,\ 30) \\
   \text{Content} &= \text{clamp}(\text{round}(0.30C),\ 0,\ 30) \\
   \text{Narrative} &= \text{clamp}(\text{round}(0.20N),\ 0,\ 20) \\
   \text{Presentation} &= \text{clamp}(\text{round}(0.10P),\ 0,\ 10) \\
   \text{Teamwork} &= \text{clamp}(\text{round}(0.10W),\ 0,\ 10)
   \end{aligned}$$

4. **S4 (NLA 平台滑桿制)**：
   $$S4_x = \text{clamp}(\text{round}(x),\ 0,\ 100), \quad \forall x \in \{T, C, N, P, W\}$$

---

## 🏛️ 系統架構與運作流程 (System Architecture)

```
                       +---------------------------------------+
                       |   使用者 (Browser @ 127.0.0.1:8000)   |
                       +-------------------+-------------------+
                                           |
                    HTTP API (Preview/Submit) | WebSocket (/ws/stream)
                                           v
+------------------------------------------------------------------------------------+
| launcher.py (Supervisor & Auto-Updater)                                             |
|   |                                                                                |
|   +--> server.py (FastAPI 微伺服器)                                                 |
|          |                                                                         |
|          +---> ScoreEngine (跨平台向度換算與清洗)                                     |
|          +---> SheetsReportManager (Google Sheets 即時排程隊列輪詢)                  |
|          +---> BrowserManager (Playwright Persistent Context)                      |
|                  |                                                                 |
|                  +-- [Page 1] S1: ChatGPT 互評站 (https://...chatgpt.site)         |
|                  +-- [Page 2] S2: Stanley Owen 評分網 (Firebase Auth)              |
|                  +-- [Page 3] S3: Google 表單 (Dynamic DOM / FormResponse)          |
|                  +-- [Page 4] S4: NLA 互評平台 (JWT Session)                       |
+------------------------------------------------------------------------------------+
```

---

## 🎮 視覺特效與趣味機制 (Visual & Easter Eggs)

1. **霓虹分數狀態回饋**：
   - 當分數 $< 60$：觸發**紅橙漸變呼吸警示 (Low Warning)**。
   - 當分數 $> 95$：觸發**彩虹流光光暈 (Rainbow Glory)**。
2. **純靜態評語卡池 (Gacha System)**：
   - 拒絕千篇一律的評語！點擊「抽評語卡池」隨機抽取 **SSR / SR / R / N** 級精緻客製化評語，並在對話框內直接帶入。
3. **Report Queue 垂直跑馬燈**：
   - 唯讀同步 Google 雲端試算表學生報告順序，具備 $5\text{ s}$ 無縫停留輪播、滑鼠滾輪直接切換與暫停功能。

---

## 🚀 快速啟動指南 (Quick Start)

本專案支援 **Windows** 與 **macOS / Linux** 雙平台「雙擊即開」，無需預先配置繁複環境！

### 🪟 Windows 使用方式
1. 下載並解壓縮發布的 ZIP 檔案。
2. 直接雙擊執行 **`run.bat`**。
3. 腳本會自動建立 `.venv`、安裝相依套件、偵測電腦內的 Chrome/Edge 核心並開啟儀表板 `http://127.0.0.1:8000`。

### 🍎 macOS 使用方式
1. 解壓縮檔案後，首次使用對 **`run.command`** 點右鍵選「打開」（或終端機執行 `chmod +x run.sh run.command`）。
2. 之後**直接雙擊 `run.command`** 即可自動啟動終端機並載入瀏覽器視窗。

### 🧑‍💻 開發者手動終端機啟動
```bash
# 1. 建立並啟動虛擬環境
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. 安裝相依套件
pip install -r requirements.txt

# 3. 安裝 Playwright 瀏覽器核心 (若電腦無 Chrome/Edge)
playwright install chromium

# 4. 執行核心啟動器守護程序
python launcher.py
```

---

## 📁 專案檔案結構 (Project Structure)

```
FillinForm/
├── core/
│   ├── __init__.py
│   ├── browser_manager.py     # Playwright 瀏覽器自動化、分頁帶出與畫面截圖廣播
│   ├── chatgpt_client.py      # S1 ChatGPT 互評站連線與評分客戶端
│   ├── firebase_client.py     # S2 Stanley Owen Firebase/Firestore 連線模組
│   ├── googleform_client.py   # S3 Google 表單動態選項解析與 POST 模組
│   ├── nla_client.py          # S4 NLA 平台 JWT 驗證與作業評分模組
│   ├── score_engine.py        # 五向度換算與邊界防禦清洗核心引擎
│   ├── sheets_client.py       # Google Sheets 學生報告隊列背景輪詢管理器
│   ├── students_data.py       # 29 位同學對照表、組別驗證與防呆邏輯
│   ├── updater.py             # 具備備份與 Rollback 機制之安全熱更新模組
│   └── version.py             # 單一真相來源版本設定檔 (Single Source of Truth)
├── static/
│   ├── css/
│   │   └── style.css          # 霓虹毛玻璃 (#0A0B10, #FF75A0, #00F5D4, #7928CA) 樣式
│   ├── js/
│   │   ├── app.js             # 儀表板互動、WebSocket 處理與表單儲存控制器
│   │   ├── gacha.js           # 評語抽卡卡池系統 (SSR / SR / R / N)
│   │   ├── mascot.js          # SVG 看板娘眨眼動畫、表情切換與對話泡泡狀態機
│   │   ├── orb_border_controller.js # 櫻花流光環繞外框與花瓣飄落物理控制器
│   │   └── score_engine.js    # 前端向度換算引擎 (與後端 100% 一致)
│   └── index.html             # 儀表板主介面 (四分割即時畫面、滑桿與控制區)
├── credentials.example.json   # 帳號憑證設定範本
├── launcher.py                # 應用程式啟動守護程序與 GitHub Release 熱更新器
├── server.py                  # FastAPI / Uvicorn 主伺服器 (僅綁定 127.0.0.1)
├── requirements.txt           # Python 相依套件清單
├── run.bat                    # Windows 一鍵啟動批次檔
├── run.command                # macOS Finder 雙擊即開啟動腳本
├── run.sh                     # macOS / Linux 終端機啟動腳本
└── 使用說明.txt               # 給終端使用者的極簡快速上手說明書
```

---

## 🛡️ 資安、防呆與隱私承諾 (Security & Anti-Fooling)

* **127.0.0.1 本機封閉**：FastAPI 微伺服器僅監聽本機迴環地址，拒絕任何外部局域網存取。
* **憑證完全本地化**：所有帳號密碼存於本機 `credentials.json`，絕不上傳第三方伺服器。
* **Git 屏蔽防線**：目錄 `profile/`、`screenshots/` 於程式啟動時自動寫入 `.gitignore`，徹底杜絕 Session Cookie 與截圖洩漏至版本控制庫。
* **預設演練模式 (Dry-Run)**：預設勾選 Dry-Run 模式，先行預填截圖供人類最終覆核，核對無誤後才允許真正送出。

---

## 🛠️ 常見問題與排解 (FAQ)

### Q1: 啟動時提示「S3 Google 表單需要登入」？
* **A**：因該表單限定 Google 帳號填答，請在儀表板點擊「前往登入 Google」按鈕，在彈出的真實瀏覽器視窗中登入一次學校或個人 Google 帳號，Session 便會永久保存在 `./profile` 目錄中，後續無需重複登入！

### Q2: 可以只送出其中某幾個平台嗎？
* **A**：可以！在點擊「送出評分」彈出的毛玻璃覆核清單中，您可以自由取消勾選任一平台（例如只想送出 S1 與 S4），系統便會自動略過未勾選的站台。

### Q3: 啟動時下載 Chromium 核心很久或逾時？
* **A**：FillinForm 內建零等待秒開技術，會自動依序調用您電腦既有的 **Google Chrome** 或 **Microsoft Edge**。只要電腦安裝有上述任一瀏覽器，即可完全免下載秒開！

---

<p align="center">
  <i>Designed with 💖 & ☕ for NTUST Students. Happy Peer Reviewing!</i>
</p>