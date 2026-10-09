/**
 * FillinForm - 主前端應用邏輯 (app.js)
 */

let mascot = null;
let currentConfig = {};
let allStudents = [];
let selectedStudent = null;
let ws = null;
let isSubmittingActive = false;

// ============================================================================
// 評分表單草稿自動儲存與還原 (Draft Storage & Restore)
// ============================================================================
function saveFormDraft() {
    try {
        const studentSelect = document.getElementById("studentSelect");
        const commentInput = document.getElementById("commentInput");
        const draft = {
            student: studentSelect ? studentSelect.value : "",
            topic: document.getElementById("sliderTopic")?.value || "85",
            content: document.getElementById("sliderContent")?.value || "85",
            narrative: document.getElementById("sliderNarrative")?.value || "85",
            presentation: document.getElementById("sliderPresentation")?.value || "85",
            teamwork: document.getElementById("sliderTeamwork")?.value || "85",
            comment: commentInput ? commentInput.value : "",
            timestamp: Date.now()
        };
        localStorage.setItem("peer_review_form_draft", JSON.stringify(draft));
    } catch (e) {
        console.warn("無法儲存草稿:", e);
    }
}

function restoreFormDraft() {
    try {
        const raw = localStorage.getItem("peer_review_form_draft");
        if (!raw) return;
        const draft = JSON.parse(raw);
        // 2 小時內草稿有效
        if (Date.now() - (draft.timestamp || 0) < 2 * 60 * 60 * 1000) {
            const studentSelect = document.getElementById("studentSelect");
            if (studentSelect && draft.student) {
                studentSelect.value = draft.student;
                if (typeof onStudentChange === "function") {
                    onStudentChange({ target: studentSelect });
                }
            }
            ["Topic", "Content", "Narrative", "Presentation", "Teamwork"].forEach(dim => {
                const slider = document.getElementById(`slider${dim}`);
                const val = draft[dim.toLowerCase()];
                if (slider && val !== undefined) {
                    slider.value = val;
                }
            });
            const commentInput = document.getElementById("commentInput");
            if (commentInput && draft.comment) {
                commentInput.value = draft.comment;
            }
            if (typeof updateScoreCalculations === "function") {
                updateScoreCalculations(false);
            }
        }
    } catch (e) {
        console.warn("還原評分草稿失敗:", e);
    }
}

// 初始化
document.addEventListener("DOMContentLoaded", () => {
    mascot = new Mascot("mascotContainer");
    initSliders();
    initGacha();
    initModal();
    initSetupModal();
    initVersionManager();
    initDynamicLayout();
    loadConfig();
    loadStudents();
    loadSheetsReport();
    initWebSocket();

    const commentInput = document.getElementById("commentInput");
    if (commentInput) {
        commentInput.addEventListener("input", saveFormDraft);
    }
    const studentSelect = document.getElementById("studentSelect");
    if (studentSelect) {
        studentSelect.addEventListener("change", saveFormDraft);
    }
    restoreFormDraft();
});

function setGradingLocked(locked) {
    const studentSelect = document.getElementById("studentSelect");
    const manualGroup = document.getElementById("manualGroupInput");
    const sliders = document.querySelectorAll(".slider-input");
    const commentInput = document.getElementById("commentInput");
    const btnGacha = document.getElementById("btnGacha");
    const btnPreview = document.getElementById("btnPreviewFill");
    const btnSubmit = document.getElementById("btnOpenReview");

    if (studentSelect) studentSelect.disabled = locked;
    if (manualGroup) manualGroup.disabled = locked;
    sliders.forEach(s => s.disabled = locked);
    if (commentInput) commentInput.disabled = locked;
    if (btnGacha) btnGacha.disabled = locked;
    if (btnPreview) btnPreview.disabled = locked;
    if (btnSubmit) btnSubmit.disabled = locked;
}

function getTargetGroup() {
    const input = document.getElementById("manualGroupInput");
    if (input && input.value) {
        const val = parseInt(input.value, 10);
        if (!isNaN(val) && val >= 1 && val <= 50) return val;
    }
    return selectedStudent ? (selectedStudent.group || 1) : 1;
}

// 載入系統設定
async function loadConfig() {
    try {
        const res = await fetch("/api/config");
        currentConfig = await res.json();
        const navInfo = document.getElementById("navUserInfo");
        if (navInfo) {
            if (currentConfig.student_id) {
                navInfo.innerText = `${currentConfig.student_name || ""} (${currentConfig.student_id})`;
            } else {
                navInfo.innerText = "未登入 (點此設定)";
            }
        }

        const warningCard = document.getElementById("loginWarningCard");
        const isLoggedIn = Boolean(currentConfig.student_id && currentConfig.has_stanleyowen_password && currentConfig.has_nla_password);
        const isSessionConfirmed = sessionStorage.getItem("quad_user_confirmed") === currentConfig.student_id;

        if (!isLoggedIn) {
            // 未登入：強制彈出設定表單，隱藏關閉按鈕，鎖定所有評分輸入
            if (warningCard) {
                warningCard.style.display = "block";
                warningCard.innerHTML = `
                    <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
                        <span style="font-size: 13px; font-weight: 700; color: var(--pink);">⚠️ 尚未完成帳號登入</span>
                        <button type="button" class="btn-tab-ctrl" id="btnWarningLogin" style="background: var(--pink); color: #fff; font-weight: 700; border: none; padding: 4px 10px; cursor: pointer;">🔐 立即登入</button>
                    </div>
                    <div style="font-size: 12px; color: var(--text-muted); margin-top: 5px; line-height: 1.4;">
                        系統處於鎖定狀態。請先輸入學號與四大平台帳號密碼進行登入驗證。
                    </div>
                `;
                const btnW = document.getElementById("btnWarningLogin");
                if (btnW) btnW.addEventListener("click", () => openSetupModal(true, "form"));
            }
            setGradingLocked(true);
            openSetupModal(true, "form");
            if (mascot) mascot.setState("WARNING", "請先完成帳號登入設定才能啟用評分功能喔！");
        } else if (!isSessionConfirmed) {
            // 已有憑證但本工作階段尚未確認身分：強制彈出身分覆核確認視圖
            if (warningCard) {
                warningCard.style.display = "block";
                warningCard.innerHTML = `
                    <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
                        <span style="font-size: 13px; font-weight: 700; color: var(--teal);">🔒 請確認評分者身分</span>
                        <button type="button" class="btn-tab-ctrl" id="btnWarningConfirm" style="background: var(--teal); color: #000; font-weight: 700; border: none; padding: 4px 10px; cursor: pointer;">📋 核對並開始評分</button>
                    </div>
                    <div style="font-size: 12px; color: var(--text-muted); margin-top: 5px; line-height: 1.4;">
                        登入已就緒，請核對您的身分資訊無誤後點擊確認，即可解鎖評分面板。
                    </div>
                `;
                const btnC = document.getElementById("btnWarningConfirm");
                if (btnC) btnC.addEventListener("click", () => openSetupModal(true, "confirm"));
            }
            setGradingLocked(true);
            openSetupModal(true, "confirm");
            if (mascot) mascot.setState("INPUT", `您好 ${currentConfig.student_name || ""}！請確認您的身分資訊與四大平台狀態～`);
        } else {
            // 已登入且已確認：完全解鎖
            if (warningCard) warningCard.style.display = "none";
            setGradingLocked(false);
        }
    } catch (e) {
        console.error("載入設定失敗:", e);
    }
}

// 載入 29 位同學清單
async function loadStudents() {
    try {
        const res = await fetch("/api/students");
        const json = await res.json();
        if (json.status === "success") {
            allStudents = json.data;
            populateStudentSelect();
        }
    } catch (e) {
        console.error("載入學生清單失敗:", e);
    }
}

function populateStudentSelect() {
    const sel = document.getElementById("studentSelect");
    if (!sel) return;
    sel.innerHTML = '<option value="">-- 請選擇受評同學 (共 29 人) --</option>';

    allStudents.forEach(s => {
        const opt = document.createElement("option");
        opt.value = s.student_id;
        let prefix = "";
        if (s.is_self) prefix = "【本人】";
        else if (s.status === "completed") prefix = "【已評】";
        else prefix = "【待評】";

        opt.innerText = `${prefix} ${s.student_id} ${s.name}`;
        if (s.is_self) {
            opt.style.color = "#FC8181";
        }
        sel.appendChild(opt);
    });

    sel.addEventListener("change", (e) => {
        onStudentChange(e);
        saveFormDraft();
    });

    // 學生清單載入完畢後，執行評分表單草稿還原
    restoreFormDraft();
}

function onStudentChange(e) {
    const sid = e.target.value;
    const btnSubmit = document.getElementById("btnOpenReview");
    const btnPreview = document.getElementById("btnPreviewFill");
    const pill = document.getElementById("targetInfoPill");
    const statusBadge = document.getElementById("targetStatusBadge");

    if (!sid) {
        selectedStudent = null;
        pill.style.display = "none";
        statusBadge.className = "badge badge-status-pending";
        statusBadge.innerText = "未選擇";
        btnSubmit.disabled = false;
        btnPreview.disabled = false;
        mascot.setState("IDLE");
        return;
    }

    selectedStudent = allStudents.find(s => s.student_id === sid);
    if (!selectedStudent) return;

    pill.style.display = "flex";
    document.getElementById("targetIdText").innerText = selectedStudent.student_id;
    document.getElementById("targetNameText").innerText = selectedStudent.name;
    // 組別僅用於 S1 且由使用者自行手動輸入，不自動覆蓋 manualGroupInput

    // 自我互評處理 (允許為自己評分)
    if (selectedStudent.is_self) {
        statusBadge.className = "badge badge-status-self";
        statusBadge.innerText = "【本人】自我互評";
        btnSubmit.disabled = false;
        btnPreview.disabled = false;
        mascot.setState("INPUT", `您選擇了為自己評分 (學號: ${selectedStudent.student_id})。`);
    } else {
        btnSubmit.disabled = false;
        btnPreview.disabled = false;

        if (selectedStudent.status === "completed") {
            statusBadge.className = "badge badge-status-completed";
            statusBadge.innerText = `已完成 (${selectedStudent.score} 分)`;
            mascot.setState("INPUT", `同學 ${selectedStudent.name} 之前已完成過，若再次送出將更新評分。`);
        } else {
            statusBadge.className = "badge badge-status-pending";
            statusBadge.innerText = "待評分";
        }
    }

    updateScoreCalculations();
}

// 初始化五向度滑桿
function initSliders() {
    const sliders = ["sliderTopic", "sliderContent", "sliderNarrative", "sliderPresentation", "sliderTeamwork"];
    sliders.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener("input", () => {
                updateScoreCalculations(true);
            });
            // 支援滑輪滾動調整分數，最低限制為 1 分，最高為 100 分
            el.addEventListener("wheel", (e) => {
                e.preventDefault();
                let current = parseFloat(el.value) || 85;
                if (e.deltaY < 0) {
                    current = Math.min(100, current + 1);
                } else {
                    current = Math.max(1, current - 1);
                }
                el.value = current;
                updateScoreCalculations(true);
            }, { passive: false });
        }
    });
    updateScoreCalculations(false);
}

function getSliderValues() {
    return {
        topic: Math.max(1, Math.min(100, parseFloat(document.getElementById("sliderTopic").value) || 85)),
        content: Math.max(1, Math.min(100, parseFloat(document.getElementById("sliderContent").value) || 85)),
        narrative: Math.max(1, Math.min(100, parseFloat(document.getElementById("sliderNarrative").value) || 85)),
        presentation: Math.max(1, Math.min(100, parseFloat(document.getElementById("sliderPresentation").value) || 85)),
        teamwork: Math.max(1, Math.min(100, parseFloat(document.getElementById("sliderTeamwork").value) || 85))
    };
}

function updateScoreBadgeFx(containerId, displayText, rawScore) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const layers = container.querySelectorAll(".score-fx-layer");
    layers.forEach(layer => {
        layer.textContent = displayText;
    });

    let nextState = "normal";
    if (rawScore < 60) {
        nextState = "low";
    } else if (rawScore > 95) {
        nextState = "high";
    }

    if (container.dataset.fxState !== nextState) {
        container.dataset.fxState = nextState;
    }
}

function updateScoreCalculations(shouldSaveDraft = false) {
    const vals = getSliderValues();
    updateScoreBadgeFx("valTopic", vals.topic.toString(), vals.topic);
    updateScoreBadgeFx("valContent", vals.content.toString(), vals.content);
    updateScoreBadgeFx("valNarrative", vals.narrative.toString(), vals.narrative);
    updateScoreBadgeFx("valPresentation", vals.presentation.toString(), vals.presentation);
    updateScoreBadgeFx("valTeamwork", vals.teamwork.toString(), vals.teamwork);

    // 前端向度計算
    const calc = ScoreEngine.calculateAll(vals.topic, vals.content, vals.narrative, vals.presentation, vals.teamwork);

    // 加權總分 (依照未經顯示四捨五入的實際數值判斷特效狀態)
    const rawWeighted = (vals.topic * 0.30 + vals.content * 0.30 + vals.narrative * 0.20 + vals.presentation * 0.10 + vals.teamwork * 0.10);
    const weightedFormatted = calc.clean_raw.weighted_total.toFixed(1);
    updateScoreBadgeFx("totalScoreText", weightedFormatted, rawWeighted);

    // 更新四平台預覽卡
    document.getElementById("prevS1").innerText = `[${calc.chatgpt.join(", ")}]`;
    document.getElementById("prevS2").innerText = `${calc.stanleyowen.total} 分 (${calc.stanleyowen.topicMastery}/${calc.stanleyowen.contentRichness}/${calc.stanleyowen.narrativeSkill}/${calc.stanleyowen.presentationSkill}/${calc.stanleyowen.teamwork})`;
    document.getElementById("prevS3").innerText = `${calc.googleform.total} 分 (${calc.googleform.topic}/${calc.googleform.content}/${calc.googleform.narrative}/${calc.googleform.presentation}/${calc.googleform.teamwork})`;
    document.getElementById("prevS4").innerText = `原值 (總分 ${calc.nla.weighted_total.toFixed(1)})`;

    if (shouldSaveDraft) {
        saveFormDraft();
    }
}

// 初始化評語抽卡
function initGacha() {
    const btnGacha = document.getElementById("btnGacha");
    if (!btnGacha) return;

    btnGacha.addEventListener("click", () => {
        const draw = GachaSystem.draw();
        const commentInput = document.getElementById("commentInput");
        const rarityText = document.getElementById("gachaRarityText");

        if (commentInput) {
            commentInput.value = draw.text;
            saveFormDraft();
        }
        if (rarityText) {
            rarityText.innerText = `[${draw.tier}]`;
            rarityText.style.color = draw.color;
        }

        mascot.setState("INPUT", `抽中 ${draw.tier} 級評語建議！已自動填入回饋框～`);
    });
}

// WebSocket 串流接收四等分即時畫面
function initWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/stream`;

    ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
        try {
            const data = jsonParseSafe(event.data);
            if (data && data.type === "quad_stream" && data.frames) {
                updateQuadFrame("S1", data.frames.S1);
                updateQuadFrame("S2", data.frames.S2);
                updateQuadFrame("S3", data.frames.S3);
                updateQuadFrame("S4", data.frames.S4);

                if (typeof data.s3_needs_login === "boolean") {
                    updateS3LoginState(data.s3_needs_login);
                }
            } else if (data && data.type === "fill_status") {
                if (window.OrbBorderController) {
                    window.OrbBorderController.setSiteState(data.site, data.status);
                }
            } else if (data && data.type === "sheets_report_update") {
                renderSheetsReport(data);
            } else if (data && data.type === "version_update") {
                if (data.data && typeof window.applyVersionInfo === "function") {
                    window.applyVersionInfo({
                        local_version: data.data.current_version,
                        latest_version: data.data.latest_version,
                        is_outdated: data.data.has_update,
                        download_url: data.data.download_url,
                        changelog: data.data.release_notes,
                        last_checked: data.data.checked_at,
                    });
                }
            }
        } catch (e) {
            console.error("處理畫面串流錯誤:", e);
        }
    };

    ws.onclose = () => {
        setTimeout(initWebSocket, 2000);
    };
}

let s3WasNeedsLogin = true; // 初次預設為未登入狀態，確保登入成功時觸發語音祝賀

function updateS3LoginState(needsLogin) {
    const banner = document.getElementById("bannerS3GoogleLogin");
    const badge = document.getElementById("btnS3LoginBadge");
    const s3StatusEl = document.getElementById("confirmStatusS3");

    if (needsLogin) {
        if (banner) banner.style.display = "flex";
        if (badge) badge.style.display = "inline-block";
        if (s3StatusEl) {
            s3StatusEl.innerHTML = "⚠️ S3: 已跳過 (需要登入 Google 帳號)";
            s3StatusEl.style.color = "#ED8936";
        }
    } else {
        if (banner) banner.style.display = "none";
        if (badge) badge.style.display = "none";
        if (s3StatusEl) {
            s3StatusEl.innerHTML = "✅ 連線正常 (29 人名單就緒)";
            s3StatusEl.style.color = "#48BB78";
        }
        // 使用者由「需要登入」變為「登入成功」時，主動提示成功了！
        if (s3WasNeedsLogin === true) {
            if (mascot && typeof mascot.setState === "function") {
                mascot.setState("SUCCESS", "🎉 成功了！S3 Google 表單登入成功，29 人名單就緒可評分～");
            }
        }
    }
    s3WasNeedsLogin = needsLogin;
}

async function openS3GoogleLogin() {
    try {
        if (mascot) mascot.setState("INPUT", "已為您呼叫 S3 Google 表單登入視窗！請在跳出的瀏覽器分頁登入您的帳號～");
        const res = await fetch("/api/s3_open_login", {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        const data = await res.json();
    } catch (e) {
        console.error("開啟 S3 登入失敗:", e);
        bringToFront("S3");
    }
}

function updateQuadFrame(siteKey, b64Data) {
    const img = document.getElementById(`img${siteKey}`);
    const loader = document.getElementById(`load${siteKey}`);
    if (img && b64Data) {
        img.src = b64Data;
        img.style.opacity = "1";
        if (loader) loader.style.display = "none";
    }
}

function jsonParseSafe(str) {
    try {
        return JSON.parse(str);
    } catch (e) {
        return null;
    }
}

// 切換至真實瀏覽器頁籤 (bring_to_front)
async function bringToFront(siteKey) {
    try {
        await fetch("/api/bring_to_front", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ site: siteKey })
        });
        mascot.speak(`已為你切換至 ${siteKey} 分頁，可在真實瀏覽器手動檢視！`);
    } catch (e) {
        console.error("切換分頁失敗:", e);
    }
}

// 縮放四等分畫面
function toggleExpand(panelId) {
    const panel = document.getElementById(panelId);
    if (panel) {
        panel.classList.toggle("expanded");
    }
}

// 填寫預覽 (填入但不送出)
document.getElementById("btnPreviewFill").addEventListener("click", async () => {
    if (!selectedStudent) {
        alert("請先選擇受評同學！");
        return;
    }

    mascot.setState("DRYRUN", "🪄 正在四個真實分頁中填入預覽內容（不送出）...");

    try {
        const payload = {
            target_id: selectedStudent.student_id,
            target_name: selectedStudent.name,
            group: getTargetGroup(),
            scores: getSliderValues(),
            comment: document.getElementById("commentInput").value
        };

        const res = await fetch("/api/preview", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.status === "success") {
            mascot.setState("DRYRUN", "🪄 四站填寫預覽完成！請確認即時畫面是否符合預期。");
        } else if (data.status === "partial_success") {
            const skipList = (data.skipped_sites || []).map(s => `• ${s}: ${data.skipped_reasons[s] || '未登入'}`).join("\n");
            mascot.setState("WARNING", `⚠️ 部分未登入平台已自動跳過填寫：\n${skipList}\n請點選頁籤完成登入！`);
            alert(`⚠️ 偵測到以下平台尚未登入或身分未確認，已自動跳過填寫：\n\n${skipList}\n\n請在右側預覽畫面點選對應分頁登入後再試！`);
        } else {
            mascot.setState("WARNING", `填寫預覽提示: ${data.detail || data.message || "部分畫面填入失敗"}`);
        }
    } catch (e) {
        mascot.setState("WARNING", `預覽操作失敗: ${e}`);
        if (window.OrbBorderController) {
            window.OrbBorderController.resetAll();
        }
    }
});

// 初始化覆核視窗 (Modal)
function initModal() {
    const modal = document.getElementById("reviewModal");
    const btnOpen = document.getElementById("btnOpenReview");
    const btnClose = document.getElementById("btnModalClose");
    const btnCancel = document.getElementById("btnModalCancel");
    const btnConfirm = document.getElementById("btnConfirmSubmit");

    btnOpen.addEventListener("click", () => {
        if (!selectedStudent) {
            alert("請先選擇受評同學！");
            return;
        }

        const vals = getSliderValues();
        const calc = ScoreEngine.calculateAll(vals.topic, vals.content, vals.narrative, vals.presentation, vals.teamwork);
        const targetGrp = getTargetGroup();

        document.getElementById("modalTargetSummary").innerText =
            `受評對象：${selectedStudent.name} (${selectedStudent.student_id}) ｜ 受評組別 (僅 S1)：第 ${targetGrp} 組 ｜ 加權總分：${calc.clean_raw.weighted_total}`;

        document.getElementById("modalValS1").innerText = `五項級分 [${calc.chatgpt.join(", ")}]`;
        document.getElementById("modalValS2").innerText = `總分 ${calc.stanleyowen.total} (${calc.stanleyowen.topicMastery}/${calc.stanleyowen.contentRichness}/${calc.stanleyowen.narrativeSkill}/${calc.stanleyowen.presentationSkill}/${calc.stanleyowen.teamwork})`;
        document.getElementById("modalValS3").innerText = `總分 ${calc.googleform.total} (自動比對下拉選單)`;
        document.getElementById("modalValS4").innerText = `原值 (加權 ${calc.nla.weighted_total})`;

        const fb = document.getElementById("modalSubmitFeedback");
        fb.style.display = "none";
        fb.innerText = "";

        modal.classList.add("active");
        mascot.setState("LAUNCH", "🚀 請逐一覆核即將送出的數值明細，確認後即可執行！");
    });

    const closeModal = () => {
        modal.classList.remove("active");
        if (mascot.currentState === "LAUNCH") {
            mascot.setState("INPUT");
        }
    };

    btnClose.addEventListener("click", closeModal);
    btnCancel.addEventListener("click", closeModal);

    btnConfirm.addEventListener("click", async () => {
        const isDryRun = document.getElementById("checkDryRun").checked;
        const excluded = [];
        if (!document.getElementById("checkS1").checked) excluded.push("S1");
        if (!document.getElementById("checkS2").checked) excluded.push("S2");
        if (!document.getElementById("checkS3").checked) excluded.push("S3");
        if (!document.getElementById("checkS4").checked) excluded.push("S4");

        const feedback = document.getElementById("modalSubmitFeedback");
        feedback.style.display = "block";
        feedback.style.background = "rgba(0, 245, 212, 0.15)";
        feedback.style.color = "var(--teal)";
        feedback.innerText = isDryRun ? "⏳ 正在執行 Dry-Run 演練模式驗證..." : "⏳ 正在逐站透過真實瀏覽器安全送出評分...";

        btnConfirm.disabled = true;
        const origBtnText = btnConfirm.innerText;
        btnConfirm.innerText = "⏳ 提交中...";
        isSubmittingActive = true;

        try {
            const payload = {
                target_id: selectedStudent.student_id,
                target_name: selectedStudent.name,
                group: getTargetGroup(),
                scores: getSliderValues(),
                comment: document.getElementById("commentInput").value,
                dry_run: isDryRun,
                excluded_sites: excluded
            };

            const res = await fetch("/api/submit", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            const data = await res.json();
            if (res.ok) {
                if (isDryRun) {
                    feedback.style.background = "rgba(0, 245, 212, 0.2)";
                    feedback.style.color = "#00F5D4";
                    feedback.innerText = "✅ Dry-Run 演練模式成功！向度換算與格式檢驗無誤，未寫入正式紀錄。";
                    mascot.setState("DRYRUN", "Dry-Run 演練無誤！若要正式提交請取消勾選演練模式。");
                } else {
                    feedback.style.background = "rgba(72, 187, 120, 0.2)";
                    feedback.style.color = "#48BB78";
                    let msg = "各平台真實瀏覽器提交狀態：\n";
                    let hasSkipped = false;
                    for (const [site, r] of Object.entries(data.results || {})) {
                        if (r.skipped) {
                            hasSkipped = true;
                            msg += `⚠️ ${site}: 已跳過 (${r.message})\n`;
                        } else {
                            msg += `• ${site}: ${r.success ? '✅ 成功 (' + r.message + ')' : '❌ 失敗 (' + (r.error || r.message) + ')'}\n`;
                        }
                    }
                    feedback.innerText = msg;
                    if (hasSkipped) {
                        feedback.style.background = "rgba(237, 137, 54, 0.2)";
                        feedback.style.color = "#ED8936";
                        mascot.setState("WARNING", "⚠️ 部分未登入平台已自動跳過送出！請完成登入後單獨補送～");
                        alert(`⚠️ 提交結果提示：\n\n部分平台因尚未登入或身分未確認，已自動跳過未送出！\n\n請在右側預覽畫面登入對應平台後，取消勾選已完成的平台單獨補送。`);
                    } else {
                        mascot.setState("SUCCESS", "🎉 評分送出完成！所有記錄已存檔！");
                    }

                    // 正式送出成功後清除已存草稿
                    localStorage.removeItem("peer_review_form_draft");

                    await loadStudents();

                    // 送出完成後將受評同學選單重設回未選擇狀態，防範連按重複提交同一位同學
                    selectedStudent = null;
                    const studentSelect = document.getElementById("studentSelect");
                    if (studentSelect) {
                        studentSelect.value = "";
                        onStudentChange({ target: studentSelect });
                    }
                }
            } else {
                feedback.style.background = "rgba(245, 101, 101, 0.2)";
                feedback.style.color = "#FC8181";
                feedback.innerText = `❌ 送出受阻: ${data.detail || "發生未預期錯誤"}`;
                mascot.setState("WARNING", `防呆或提交警示: ${data.detail}`);
            }
        } catch (e) {
            feedback.style.background = "rgba(245, 101, 101, 0.2)";
            feedback.style.color = "#FC8181";
            feedback.innerText = `連線錯誤: ${e}`;
            mascot.setState("WARNING", "連線伺服器失敗，請確認後端是否運行。");
        } finally {
            btnConfirm.disabled = false;
            btnConfirm.innerText = origBtnText;
            isSubmittingActive = false;
        }
    });
}

// 帳號密碼設定與身分覆核視窗
function openSetupModal(isMandatory = false, defaultView = "form") {
    const modal = document.getElementById("setupModal");
    if (!modal) return;

    const btnClose = document.getElementById("btnSetupClose");
    const btnCancel = document.getElementById("btnSetupCancel");
    const title = document.getElementById("setupModalTitle");
    const formView = document.getElementById("setupFormView");
    const confirmView = document.getElementById("setupConfirmView");

    // 強制模式控制關閉按鈕顯隱
    if (isMandatory) {
        if (btnClose) btnClose.style.display = "none";
        if (btnCancel) btnCancel.style.display = "none";
    } else {
        if (btnClose) btnClose.style.display = "block";
        if (btnCancel) btnCancel.style.display = "block";
    }

    // 填入表單欄位
    document.getElementById("setupStudentId").value = currentConfig.student_id || "";
    document.getElementById("setupStudentName").value = currentConfig.student_name || "";
    document.getElementById("setupEmail").value = currentConfig.email || "";
    document.getElementById("setupS2Email").value = currentConfig.stanleyowen_email || (currentConfig.student_id ? `${currentConfig.student_id.toLowerCase()}@mail.ntust.edu.tw` : "");

    // 填入確認視圖欄位
    document.getElementById("confirmStudentId").innerText = currentConfig.student_id || "-";
    document.getElementById("confirmStudentName").innerText = currentConfig.student_name || "-";
    document.getElementById("confirmEmail").innerText = currentConfig.email || "-";
    document.getElementById("confirmS2Email").innerText = currentConfig.stanleyowen_email || (currentConfig.student_id ? `${currentConfig.student_id.toLowerCase()}@mail.ntust.edu.tw` : "-");

    const fb = document.getElementById("setupFeedback");
    if (fb) {
        fb.style.display = "none";
        fb.innerText = "";
    }

    const s3StatusEl = document.getElementById("confirmStatusS3");
    if (s3StatusEl) {
        if (s3WasNeedsLogin === false) {
            s3StatusEl.innerHTML = "✅ S3: 登入成功";
            s3StatusEl.style.color = "#48BB78";
        } else {
            s3StatusEl.innerHTML = "⚠️ S3: 已跳過 (需要登入 Google 帳號)";
            s3StatusEl.style.color = "#ED8936";
        }
    }

    if (defaultView === "confirm") {
        if (title) title.innerText = "📋 評分者身分與四大平台狀態覆核";
        if (formView) formView.style.display = "none";
        if (confirmView) confirmView.style.display = "flex";
    } else {
        if (title) title.innerText = isMandatory ? "🔐 初次使用：強制登入設定" : "⚙️ 帳號登入與平台設定";
        if (formView) formView.style.display = "block";
        if (confirmView) confirmView.style.display = "none";
    }

    modal.classList.add("active");
}

function initSetupModal() {
    const modal = document.getElementById("setupModal");
    const btnNavSetup = document.getElementById("btnNavSetup");
    const btnClose = document.getElementById("btnSetupClose");
    const btnCancel = document.getElementById("btnSetupCancel");
    const btnSave = document.getElementById("btnSaveSetup");
    const idInput = document.getElementById("setupStudentId");
    const btnQueryName = document.getElementById("btnAutoQueryName");
    const s2EmailInput = document.getElementById("setupS2Email");
    const nameInput = document.getElementById("setupStudentName");
    const btnConfirmStart = document.getElementById("btnConfirmStart");
    const btnBackToSetupForm = document.getElementById("btnBackToSetupForm");

    if (btnNavSetup) {
        btnNavSetup.addEventListener("click", () => openSetupModal(false, "confirm"));
    }
    const userBadge = document.getElementById("userBadge");
    if (userBadge) {
        userBadge.addEventListener("click", () => openSetupModal(false, "confirm"));
        userBadge.style.cursor = "pointer";
    }

    const closeModal = () => {
        if (modal) modal.classList.remove("active");
    };

    if (btnClose) btnClose.addEventListener("click", closeModal);
    if (btnCancel) btnCancel.addEventListener("click", closeModal);

    // 切換回修改設定表單
    if (btnBackToSetupForm) {
        btnBackToSetupForm.addEventListener("click", () => {
            const formView = document.getElementById("setupFormView");
            const confirmView = document.getElementById("setupConfirmView");
            const title = document.getElementById("setupModalTitle");
            if (formView) formView.style.display = "block";
            if (confirmView) confirmView.style.display = "none";
            if (title) title.innerText = "⚙️ 帳號登入與平台設定";
        });
    }

    // 「🚀 確認無誤，開始評分！」按鈕事件
    if (btnConfirmStart) {
        btnConfirmStart.addEventListener("click", () => {
            if (currentConfig.student_id) {
                sessionStorage.setItem("quad_user_confirmed", currentConfig.student_id);
            }
            closeModal();
            const warningCard = document.getElementById("loginWarningCard");
            if (warningCard) warningCard.style.display = "none";
            setGradingLocked(false);
            if (mascot) {
                mascot.setState("SUCCESS", `🎉 身分覆核確認完成！${currentConfig.student_name || ""} 同學，已為您解鎖評分系統！`);
            }
        });
    }

    // 輸入學號時自動連動學校信箱
    if (idInput && s2EmailInput) {
        idInput.addEventListener("input", (e) => {
            const sid = e.target.value.trim().toLowerCase();
            if (sid) {
                s2EmailInput.value = `${sid}@mail.ntust.edu.tw`;
            }
        });
    }

    // 查名按鈕
    if (btnQueryName && idInput && nameInput) {
        btnQueryName.addEventListener("click", async () => {
            const sid = idInput.value.trim();
            if (!sid) {
                alert("請先輸入學號！");
                return;
            }
            btnQueryName.innerText = "查詢中...";
            try {
                const res = await fetch(`/api/query_name?id=${encodeURIComponent(sid)}`);
                const data = await res.json();
                if (data.status === "success" && data.name) {
                    nameInput.value = data.name;
                    mascot.speak(`查得姓名：${data.name}！已自動帶入～`);
                } else {
                    alert("S1 與名單中未找到此學號姓名，請手動輸入。");
                }
            } catch (err) {
                alert("查詢姓名失敗，請手動填寫。");
            } finally {
                btnQueryName.innerText = "🔍 查名";
            }
        });
    }

    // 儲存並在瀏覽器驗證登入
    if (btnSave) {
        btnSave.addEventListener("click", async () => {
            const studentId = idInput.value.trim().toUpperCase();
            const studentName = nameInput.value.trim();
            const email = document.getElementById("setupEmail").value.trim();
            const s2Email = s2EmailInput.value.trim();
            const s2Pwd = document.getElementById("setupS2Password").value.trim();
            const s4Pwd = document.getElementById("setupS4Password").value.trim();

            if (!studentId) {
                alert("請填寫學號！");
                return;
            }
            if (!studentName) {
                alert("請填寫姓名！");
                return;
            }
            if (!email) {
                alert("請填寫 Google 表單電子郵件！");
                return;
            }

            const feedback = document.getElementById("setupFeedback");
            feedback.style.display = "block";
            feedback.style.background = "rgba(0, 245, 212, 0.15)";
            feedback.style.color = "var(--teal)";
            feedback.innerText = "⏳ 正在驗證登入並同步至真實瀏覽器（約需 3~5 秒）...";
            btnSave.disabled = true;

            try {
                const payload = {
                    student_id: studentId,
                    student_name: studentName,
                    email: email,
                    stanleyowen_email: s2Email,
                    stanleyowen_password: s2Pwd,
                    nla_password: s4Pwd
                };

                const res = await fetch("/api/setup", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();

                if (res.ok) {
                    feedback.style.background = "rgba(72, 187, 120, 0.2)";
                    feedback.style.color = "#48BB78";
                    feedback.innerText = `✅ ${data.message}`;

                    await loadConfig();
                    await loadStudents();

                    // 更新確認視圖欄位與平台狀態
                    document.getElementById("confirmStudentId").innerText = studentId;
                    document.getElementById("confirmStudentName").innerText = studentName;
                    document.getElementById("confirmEmail").innerText = email;
                    document.getElementById("confirmS2Email").innerText = s2Email;

                    const checks = data.checks || {};
                    const s1El = document.getElementById("confirmStatusS1");
                    const s2El = document.getElementById("confirmStatusS2");
                    const s3El = document.getElementById("confirmStatusS3");
                    const s4El = document.getElementById("confirmStatusS4");

                    if (s1El) s1El.innerHTML = checks.S1 ? "✅ 已查詢姓名並進駐評分頁" : "⚠️ 連線中 (請稍候)";
                    if (s2El) s2El.innerHTML = checks.S2 ? "✅ 帳號認證成功 (已登入)" : "⚠️ 登入未通過";
                    if (s3El) {
                        const s3LoggedIn = (checks.S3 && checks.S3_login_needed === false) || s3WasNeedsLogin === false;
                        if (s3LoggedIn) {
                            s3El.innerHTML = "✅ S3: 登入成功";
                            s3El.style.color = "#48BB78";
                        } else {
                            s3El.innerHTML = "⚠️ S3: 已跳過 (需要登入 Google 帳號)";
                            s3El.style.color = "#ED8936";
                        }
                    }
                    if (s4El) s4El.innerHTML = checks.S4 ? "✅ Session 認證有效" : "⚠️ 認證未通過";

                    // 切換至身分覆核視圖，要求使用者確認
                    setTimeout(() => {
                        feedback.style.display = "none";
                        const formView = document.getElementById("setupFormView");
                        const confirmView = document.getElementById("setupConfirmView");
                        const title = document.getElementById("setupModalTitle");
                        if (formView) formView.style.display = "none";
                        if (confirmView) confirmView.style.display = "flex";
                        if (title) title.innerText = "📋 評分者身分與四大平台狀態覆核";
                        if (mascot) mascot.setState("INPUT", "登入成功！請覆核您的身分資訊，確認無誤後點擊「開始評分」！");
                    }, 1200);
                } else {
                    feedback.style.background = "rgba(245, 101, 101, 0.2)";
                    feedback.style.color = "#FC8181";
                    feedback.innerText = `❌ 設定失敗: ${data.detail || "伺服器錯誤"}`;
                    mascot.setState("WARNING", `登入驗證提示: ${data.detail}`);
                }
            } catch (err) {
                feedback.style.background = "rgba(245, 101, 101, 0.2)";
                feedback.style.color = "#FC8181";
                feedback.innerText = `連線錯誤: ${err}`;
            } finally {
                btnSave.disabled = false;
            }
        });
    }

    // 初始化密碼顯示/隱藏切換功能 (👁️ / 🙈)
    document.querySelectorAll(".btn-toggle-pwd").forEach(btn => {
        btn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            const targetId = btn.getAttribute("data-target");
            const input = document.getElementById(targetId);
            if (!input) return;
            if (input.type === "password") {
                input.type = "text";
                btn.classList.add("is-visible");
                btn.innerText = "🙈";
                btn.title = "隱藏密碼";
            } else {
                input.type = "password";
                btn.classList.remove("is-visible");
                btn.innerText = "👁️";
                btn.title = "顯示密碼";
            }
        });
    });
}

// ============================================================================
// 版本號膠囊與更新管理器 (Version Capsule & Release Modal)
// ============================================================================
let currentVersionInfo = {
    local_version: "",
    latest_version: "",
    is_outdated: false,
    download_url: "",
    changelog: "",
    last_checked: "剛剛"
};
let hasNotifiedOutdated = false;

function applyVersionInfo(info) {
    if (!info) return;
    currentVersionInfo = { ...currentVersionInfo, ...info };

    const navCapsule = document.getElementById("navVersionCapsule");
    const navText = document.getElementById("navVersionText");
    const navStatusPill = document.getElementById("navVersionStatusPill");
    const navAlertBadge = document.getElementById("navVersionAlertBadge");

    const modalLocalVersion = document.getElementById("modalLocalVersion");
    const modalLocalStatus = document.getElementById("modalLocalStatus");
    const modalLatestVersion = document.getElementById("modalLatestVersion");
    const modalLatestStatus = document.getElementById("modalLatestStatus");
    const statusBanner = document.getElementById("versionStatusBanner");
    const bannerIcon = document.getElementById("statusBannerIcon");
    const bannerText = document.getElementById("statusBannerText");
    const changelogCard = document.getElementById("versionChangelogCard");
    const changelogContent = document.getElementById("modalChangelogContent");
    const lastCheckedEl = document.getElementById("modalLastCheckedTime");
    const btnDoAutoUpdate = document.getElementById("btnDoAutoUpdate");
    const btnUpdateLater = document.getElementById("btnUpdateLater");

    const localVer = currentVersionInfo.local_version || "";
    const latestVer = currentVersionInfo.latest_version || localVer;
    const isOutdated = !!currentVersionInfo.is_outdated;

    const localDisplay = localVer ? ("v" + String(localVer).replace(/^v/i, "")) : "v--";
    const latestDisplay = latestVer ? ("v" + String(latestVer).replace(/^v/i, "")) : "v--";

    // 1. 更新頂部導航列版本膠囊
    if (navText) navText.textContent = localDisplay;

    if (navCapsule) {
        if (isOutdated) {
            navCapsule.classList.add("is-outdated");
            if (navStatusPill) navStatusPill.textContent = `請更新至 ${latestDisplay}`;
            if (navAlertBadge) navAlertBadge.style.display = "inline-flex";
            navCapsule.title = `⚠️ 發現新版本 ${latestDisplay}！點擊即可一鍵更新並重啟`;

            // 看板娘主動提示一次
            if (!hasNotifiedOutdated && mascot && typeof mascot.setState === "function") {
                hasNotifiedOutdated = true;
                mascot.setState("WARNING", `💡 發現新版本 ${latestDisplay}！點擊頂部版本號即可一鍵自動更新重啟～`);
            }
        } else {
            navCapsule.classList.remove("is-outdated");
            if (navStatusPill) navStatusPill.textContent = "最新";
            if (navAlertBadge) navAlertBadge.style.display = "none";
            navCapsule.title = `目前已是最新版本 (${localDisplay})，點擊檢視版本詳情`;
        }
    }

    // 2. 更新彈窗內部數值
    if (modalLocalVersion) modalLocalVersion.textContent = localDisplay;
    if (modalLatestVersion) modalLatestVersion.textContent = latestDisplay;

    if (modalLocalStatus) {
        modalLocalStatus.textContent = isOutdated ? "有新版" : "使用中";
        modalLocalStatus.style.color = isOutdated ? "#F87171" : "#A0AEC0";
    }

    if (modalLatestStatus) {
        modalLatestStatus.textContent = isOutdated ? "可一鍵更新" : "已同步最新";
        modalLatestStatus.style.color = "#34D399";
    }

    if (lastCheckedEl && currentVersionInfo.last_checked) {
        lastCheckedEl.textContent = currentVersionInfo.last_checked;
    }

    if (statusBanner && bannerIcon && bannerText) {
        if (isOutdated) {
            statusBanner.className = "version-status-banner is-outdated";
            bannerIcon.textContent = "⚠️";
            bannerText.innerHTML = `發現新版本 <strong>${escapeHtml(latestDisplay)}</strong> 可用！點擊下方按鈕即可自動下載套用並重啟。`;
            if (btnDoAutoUpdate) btnDoAutoUpdate.style.display = "inline-flex";
            if (btnUpdateLater) btnUpdateLater.textContent = "稍後提醒";
        } else {
            statusBanner.className = "version-status-banner";
            bannerIcon.textContent = "✅";
            bannerText.textContent = `目前已是最新版本 (${localDisplay})！所有功能正常運作中。`;
            if (btnDoAutoUpdate) btnDoAutoUpdate.style.display = "none";
            if (btnUpdateLater) btnUpdateLater.textContent = "確定關閉";
        }
    }

    // 3. 更新說明
    if (changelogCard && changelogContent) {
        if (currentVersionInfo.changelog && currentVersionInfo.changelog.trim()) {
            changelogCard.style.display = "block";
            changelogContent.textContent = currentVersionInfo.changelog.trim();
        } else {
            changelogCard.style.display = "none";
        }
    }
}
window.applyVersionInfo = applyVersionInfo;

function initVersionManager() {
    const navCapsule = document.getElementById("navVersionCapsule");
    const modal = document.getElementById("versionModal");
    const btnClose = document.getElementById("btnVersionModalClose");
    const btnRefresh = document.getElementById("btnVersionRefresh");
    const btnDoAutoUpdate = document.getElementById("btnDoAutoUpdate");
    const btnUpdateLater = document.getElementById("btnUpdateLater");

    const openModal = () => {
        if (!modal) return;
        applyVersionInfo(currentVersionInfo);
        modal.classList.add("active");
    };

    const closeModal = () => {
        if (!modal) return;
        modal.classList.remove("active");
    };

    if (navCapsule) {
        navCapsule.addEventListener("click", openModal);
    }
    if (btnClose) {
        btnClose.addEventListener("click", closeModal);
    }
    if (btnUpdateLater) {
        btnUpdateLater.addEventListener("click", closeModal);
    }
    if (modal) {
        modal.addEventListener("click", (e) => {
            if (e.target === modal) closeModal();
        });
    }

    // 一鍵自動更新並重啟
    if (btnDoAutoUpdate) {
        btnDoAutoUpdate.addEventListener("click", async () => {
            if (isSubmittingActive) {
                alert("⚠️ 目前系統正在提交評分中，為保護資料完整，請於提交完成後再進行更新！");
                return;
            }

            const targetVer = currentVersionInfo.latest_version || "最新版本";
            if (!confirm(`確定要立即更新至 v${targetVer.replace(/^v/i, '')} 並重新啟動嗎？\n\n系統將自動保存您目前的評分草稿與個人設定。`)) {
                return;
            }

            // 1. 保存當前評分表單草稿
            saveFormDraft();

            // 2. 顯示全螢幕重啟進度遮罩
            const overlay = document.getElementById("updateProgressOverlay");
            const statusEl = document.getElementById("updateOverlayStatus");
            const subEl = document.getElementById("updateOverlaySub");
            if (overlay) overlay.style.display = "flex";
            closeModal();

            try {
                // 3. 送出後端更新請求 (觸發 Exit Code 42 由 launcher 接手)
                const resp = await fetch("/api/system/request_update", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        download_url: currentVersionInfo.download_url,
                        target_version: currentVersionInfo.latest_version
                    })
                });

                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(err.detail || "伺服器拒絕更新請求");
                }
            } catch (e) {
                alert("發起更新失敗: " + e.message);
                if (overlay) overlay.style.display = "none";
                return;
            }

            // 4. 等候舊伺服器釋放與 launcher 替換，並啟動指數退避輪詢重連
            let attempts = 0;
            const maxAttempts = 40;
            const checkInterval = 1500;

            if (subEl) subEl.textContent = "伺服器重啟中，正在等待新版服務就緒 (1/40)...";

            await new Promise(r => setTimeout(r, 2000));

            const pollTimer = setInterval(async () => {
                attempts++;
                if (subEl) subEl.textContent = `伺服器重啟中，正在等待新版服務就緒 (${attempts}/${maxAttempts})...`;

                try {
                    const r = await fetch("/api/config?t=" + Date.now(), { cache: "no-store" });
                    if (r.ok) {
                        const cfg = await r.json();
                        clearInterval(pollTimer);
                        if (statusEl) statusEl.textContent = "🎉 新版伺服器已就緒！正在重新整理頁面並載入新功能...";
                        if (subEl) subEl.textContent = `目前版本：v${cfg.app_version || '最新'}`;
                        setTimeout(() => {
                            // 強制帶時間戳與版本號重載，完全消除瀏覽器舊快取
                            window.location.replace(window.location.pathname + '?_v=' + (cfg.app_version || Date.now()) + '&_t=' + Date.now());
                        }, 800);
                    }
                } catch (err) {
                    if (attempts >= maxAttempts) {
                        clearInterval(pollTimer);
                        if (statusEl) statusEl.innerHTML = "⚠️ 重連逾時，但背景更新可能已完成。<br>請稍後點擊下方按鈕強制重新整理！";
                        if (subEl) subEl.innerHTML = `<button onclick="window.location.replace(window.location.pathname + '?_t=' + Date.now())" style="background:#2DD4BF;color:#000;border:none;padding:6px 14px;border-radius:6px;cursor:pointer;font-weight:700;margin-top:10px;">強制重新整理 (清除快取)</button>`;
                    }
                }
            }, checkInterval);
        });
    }

    if (btnRefresh) {
        btnRefresh.addEventListener("click", async () => {
            btnRefresh.disabled = true;
            const origText = btnRefresh.textContent;
            btnRefresh.textContent = "⏳ 檢查中...";
            try {
                const resp = await fetch("/api/system/update_status");
                if (resp.ok) {
                    const data = await resp.json();
                    applyVersionInfo({
                        local_version: data.current_version,
                        latest_version: data.latest_version,
                        is_outdated: data.has_update,
                        download_url: data.download_url,
                        changelog: data.release_notes,
                        last_checked: data.checked_at,
                    });
                    if (mascot) mascot.setState("NORMAL", data.has_update ? "🔔 發現新版本！可點擊一鍵更新升級～" : "✨ 目前已是最新版本！");
                }
            } catch (e) {
                console.error("更新檢查失敗:", e);
            } finally {
                btnRefresh.disabled = false;
                btnRefresh.textContent = origText;
            }
        });
    }

    // 首次載入取得版本
    fetch("/api/version")
        .then(r => r.json())
        .then(data => applyVersionInfo(data))
        .catch(err => console.warn("載入版本資訊失敗:", err));
}

// 動態調整版面大小與排版模式
function initDynamicLayout() {
    // 1. 拖曳調整左右欄寬度
    const resizer = document.getElementById("mainResizer");
    const controlPanel = document.querySelector(".control-panel");
    const container = document.querySelector(".main-container");

    if (resizer && controlPanel && container) {
        // 恢復歷史寬度
        const savedWidth = localStorage.getItem("quad_panel_width");
        if (savedWidth) {
            const w = parseInt(savedWidth, 10);
            if (!isNaN(w) && w >= 320 && w <= 850) {
                controlPanel.style.width = `${w}px`;
            }
        }

        let isDragging = false;
        resizer.addEventListener("mousedown", (e) => {
            isDragging = true;
            resizer.classList.add("dragging");
            document.body.style.cursor = "col-resize";
            document.body.style.userSelect = "none";
        });

        document.addEventListener("mousemove", (e) => {
            if (!isDragging) return;
            const containerRect = container.getBoundingClientRect();
            let newWidth = e.clientX - containerRect.left;
            if (newWidth < 320) newWidth = 320;
            if (newWidth > 850) newWidth = 850;
            controlPanel.style.width = `${newWidth}px`;
        });

        document.addEventListener("mouseup", () => {
            if (isDragging) {
                isDragging = false;
                resizer.classList.remove("dragging");
                document.body.style.cursor = "";
                document.body.style.userSelect = "";
                localStorage.setItem("quad_panel_width", controlPanel.offsetWidth);
            }
        });

        // 雙擊重設為 480px
        resizer.addEventListener("dblclick", () => {
            controlPanel.style.width = "480px";
            localStorage.setItem("quad_panel_width", "480");
        });
    }

    // 2. 畫面縮放控制 (預設 100% 原始大小，文字清晰不縮放)
    const zoomBtns = document.querySelectorAll(".btn-zoom-scale");
    zoomBtns.forEach((btn) => {
        btn.addEventListener("click", () => {
            zoomBtns.forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
            const scale = btn.getAttribute("data-scale") || "1.0";
            if (scale === "1.0") {
                document.body.style.zoom = "";
            } else {
                document.body.style.zoom = scale;
            }
            localStorage.setItem("quad_ui_zoom_v3", scale);
        });
    });

    const savedZoom = localStorage.getItem("quad_ui_zoom_v3") || "1.0";
    const defaultBtn = document.querySelector(`.btn-zoom-scale[data-scale="${savedZoom}"]`);
    if (defaultBtn) defaultBtn.click();

    // 3. 四等分排版模式切換 (網格 / 焦點放大 / 垂直雙欄)
    const quadContainer = document.getElementById("quadContainer");
    const btnGrid = document.getElementById("btnLayoutGrid");
    const btnFocus = document.getElementById("btnLayoutFocus");
    const btnStack = document.getElementById("btnLayoutStack");
    const focusTabs = document.querySelectorAll(".quad-focus-tab");

    const setLayoutMode = (mode) => {
        if (!quadContainer) return;
        quadContainer.className = `quad-grid-container mode-${mode}`;
        [btnGrid, btnFocus, btnStack].forEach((b) => {
            if (b) b.classList.remove("active");
        });
        if (mode === "grid" && btnGrid) btnGrid.classList.add("active");
        if (mode === "focus" && btnFocus) btnFocus.classList.add("active");
        if (mode === "stack" && btnStack) btnStack.classList.add("active");
        localStorage.setItem("quad_layout_mode", mode);
    };

    if (btnGrid) btnGrid.addEventListener("click", () => setLayoutMode("grid"));
    if (btnFocus) btnFocus.addEventListener("click", () => setLayoutMode("focus"));
    if (btnStack) btnStack.addEventListener("click", () => setLayoutMode("stack"));

    // 焦點模式分頁標籤點擊
    focusTabs.forEach((tab) => {
        tab.addEventListener("click", () => {
            focusTabs.forEach((t) => t.classList.remove("active"));
            tab.classList.add("active");
            const targetId = tab.getAttribute("data-target");
            document.querySelectorAll(".quad-panel").forEach((p) => p.classList.remove("focus-active"));
            const targetPanel = document.getElementById(targetId);
            if (targetPanel) targetPanel.classList.add("focus-active");
        });
    });

    const savedMode = localStorage.getItem("quad_layout_mode") || "grid";
    setLayoutMode(savedMode);
}

// ============================================================================
// Google Sheets 學生報告資訊唯讀元件處理
// ============================================================================

function escapeHtml(text) {
    if (text === null || text === undefined) return "";
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

async function loadSheetsReport() {
    try {
        const resp = await fetch("/api/sheets_report");
        if (resp.ok) {
            const data = await resp.json();
            renderSheetsReport(data);
        }
    } catch (e) {
        console.error("載入雲端報告狀態失敗:", e);
    }
}

// ============================================================================
// Google Sheets 學生報告組別垂直跑馬燈 (無縫循環、滾輪加速、NLA 風格)
// ============================================================================

class VerticalMarqueeController {
    constructor() {
        this.card = document.getElementById("sheetsReportCard");
        this.viewport = document.getElementById("sheetsMarqueeViewport");
        this.track = document.getElementById("sheetsMarqueeTrack");
        this.badge = document.getElementById("sheetsReportStatusBadge");
        this.syncTime = document.getElementById("sheetsReportSyncTime");
        this.notice = document.getElementById("sheetsReportNotice");
        this.btnPrev = document.getElementById("btnMarqueePrev");
        this.btnNext = document.getElementById("btnMarqueeNext");
        this.btnPlayPause = document.getElementById("btnMarqueePlayPause");
        this.indicator = document.getElementById("marqueeIndexIndicator");

        this.groups = [];
        this.currentIndex = 1; // 1-indexed into track.children (0 is clone of last)
        this.isTransitioning = false;
        this.isPaused = false;
        this.timer = null;
        this.stayDuration = 5000; // 5 秒完整閱讀停留
        this.transitionDuration = 500; // 500ms 平順切換動畫

        this.accumulatedDelta = 0;
        this.wheelResetTimer = null;

        this.initControls();
    }

    initControls() {
        if (!this.viewport || !this.track) return;

        // 1. 小型閱讀控制按鈕
        if (this.btnPrev) {
            this.btnPrev.addEventListener("click", () => {
                if (this.groups.length >= 2 && !this.isTransitioning) {
                    this.slidePrev(true);
                }
            });
        }
        if (this.btnNext) {
            this.btnNext.addEventListener("click", () => {
                if (this.groups.length >= 2 && !this.isTransitioning) {
                    this.slideNext(true);
                }
            });
        }
        if (this.btnPlayPause) {
            this.btnPlayPause.addEventListener("click", () => {
                this.togglePlayPause();
            });
        }

        // 2. 軌道 transitionend 事件 (無縫銜接瞬跳重置)
        this.track.addEventListener("transitionend", (e) => {
            if (e.target !== this.track || e.propertyName !== "transform") return;
            this.handleTransitionEnd();
        });

        // 3. 滾輪加速換組 (在跑馬燈區塊內且至少 2 組時攔截)
        const handleWheel = (e) => {
            if (this.groups.length < 2) return;

            e.preventDefault();
            e.stopPropagation();

            if (this.isTransitioning) return;

            this.accumulatedDelta += e.deltaY;

            if (this.wheelResetTimer) clearTimeout(this.wheelResetTimer);
            this.wheelResetTimer = setTimeout(() => {
                this.accumulatedDelta = 0;
            }, 250);

            const THRESHOLD = 30; // 觸控板與滾輪平順門檻
            if (this.accumulatedDelta >= THRESHOLD) {
                this.accumulatedDelta = 0;
                this.slideNext(true);
            } else if (this.accumulatedDelta <= -THRESHOLD) {
                this.accumulatedDelta = 0;
                this.slidePrev(true);
            }
        };

        const wheelTarget = this.card || this.viewport;
        if (wheelTarget) {
            wheelTarget.addEventListener("wheel", handleWheel, { passive: false });
        }
    }

    togglePlayPause() {
        this.isPaused = !this.isPaused;
        if (this.btnPlayPause) {
            const pauseTag = document.getElementById("marqueePausedTag");
            const icon = this.btnPlayPause.querySelector(".play-state-icon");
            if (this.isPaused) {
                if (icon) icon.textContent = "▶";
                if (pauseTag) pauseTag.style.display = "inline";
                this.btnPlayPause.title = "繼續自動輪播";
                this.btnPlayPause.classList.add("is-paused");
                this.clearTimer();
            } else {
                if (icon) icon.textContent = "⏸";
                if (pauseTag) pauseTag.style.display = "none";
                this.btnPlayPause.title = "暫停自動輪播";
                this.btnPlayPause.classList.remove("is-paused");
                if (this.groups.length >= 2 && !this.isTransitioning) {
                    this.scheduleNextStay();
                }
            }
        }
    }

    clearTimer() {
        if (this.timer) {
            clearTimeout(this.timer);
            this.timer = null;
        }
    }

    scheduleNextStay() {
        this.clearTimer();
        if (this.isPaused || this.groups.length < 2) return;
        this.timer = setTimeout(() => {
            if (!this.isPaused && !this.isTransitioning && this.groups.length >= 2) {
                this.slideNext(false);
            }
        }, this.stayDuration);
    }

    getCardOffset(index) {
        const cards = this.track.children;
        if (!cards || cards.length === 0) return 0;
        const targetCard = cards[index];
        if (!targetCard) return 0;
        const trackPaddingTop = parseFloat(window.getComputedStyle(this.track).paddingTop) || 0;
        return targetCard.offsetTop - trackPaddingTop;
    }

    applyTransform(animated) {
        if (!this.track) return;
        if (animated) {
            this.track.style.transition = `transform ${this.transitionDuration}ms cubic-bezier(0.25, 1, 0.5, 1)`;
        } else {
            this.track.style.transition = "none";
        }
        const offset = this.getCardOffset(this.currentIndex);
        this.track.style.transform = `translateY(-${offset}px)`;

        // 更新 active 高亮定位線 (僅中央卡片有 2px 青色定位線與微弱底色)
        if (this.track.children) {
            Array.from(this.track.children).forEach((card, idx) => {
                if (idx === this.currentIndex) {
                    card.classList.add("is-active");
                } else {
                    card.classList.remove("is-active");
                }
            });
        }
    }

    slideNext(isManual = false) {
        if (this.isTransitioning || this.groups.length < 2) return;
        this.clearTimer();
        this.isTransitioning = true;
        this.currentIndex++;
        this.applyTransform(true);
        this.updateIndicator();
    }

    slidePrev(isManual = false) {
        if (this.isTransitioning || this.groups.length < 2) return;
        this.clearTimer();
        this.isTransitioning = true;
        this.currentIndex--;
        this.applyTransform(true);
        this.updateIndicator();
    }

    handleTransitionEnd() {
        const total = this.groups.length;
        if (total < 2) {
            this.isTransitioning = false;
            return;
        }

        // 首尾無縫循環接點瞬切 (無閃爍、無倒滑回捲)
        if (this.currentIndex === total + 1) {
            this.currentIndex = 1;
            this.applyTransform(false);
            void this.track.offsetHeight;
        } else if (this.currentIndex === 0) {
            this.currentIndex = total;
            this.applyTransform(false);
            void this.track.offsetHeight;
        }

        this.isTransitioning = false;
        this.updateIndicator();

        // 完成位移後完整停留 5 秒
        if (!this.isPaused) {
            this.scheduleNextStay();
        }
    }

    updateIndicator() {
        if (!this.indicator) return;
        const total = this.groups.length;
        if (total === 0) {
            this.indicator.textContent = "";
            return;
        }
        let realIndex = 1;
        if (total >= 2) {
            if (this.currentIndex === 0) {
                realIndex = total;
            } else if (this.currentIndex === total + 1) {
                realIndex = 1;
            } else {
                realIndex = this.currentIndex;
            }
        }
        const realStr = String(realIndex).padStart(2, "0");
        const totStr = String(total).padStart(2, "0");
        this.indicator.textContent = `QUEUE ${realStr} / ${totStr}`;
    }

    renderCardHtml(group) {
        const numInt = parseInt(group.group_id, 10);
        const numStr = isNaN(numInt) ? String(group.group_id) : String(numInt).padStart(2, "0");
        const groupNameCn = group.group_name || `第 ${numInt || group.group_id} 組`;

        const membersHtml = (group.members || []).map(m => {
            const sid = escapeHtml(m.student_id);
            const name = escapeHtml(m.name);
            let orderHtml = "";
            if (m.report_order !== null && m.report_order !== undefined && String(m.report_order).trim() !== "") {
                const ordInt = parseInt(m.report_order, 10);
                const ordStr = isNaN(ordInt) ? escapeHtml(m.report_order) : String(ordInt).padStart(2, "0");
                orderHtml = `<span class="member-order" title="報告順序">#${ordStr}</span>`;
            }

            return `<div class="member-row">
                <div class="member-identity">
                    <span class="member-name">${name}</span>
                    <span class="member-sid">${sid}</span>
                </div>
                ${orderHtml}
            </div>`;
        }).join("");

        return `<div class="queue-card">
            <!-- [A] 組別識別區 -->
            <div class="queue-col-group">
                <span class="group-num">${numStr}</span>
                <span class="group-tag">GROUP</span>
                <span class="group-cn">${escapeHtml(groupNameCn)}</span>
            </div>
            <!-- [B] 成員資訊區 -->
            <div class="queue-col-members">
                ${membersHtml}
            </div>
            <!-- [C] 報告狀態區 -->
            <div class="queue-col-status">
                <div class="status-capsule reported">
                    <span class="capsule-dot"></span>
                    <span class="capsule-text">已報告</span>
                </div>
            </div>
        </div>`;
    }

    updateData(payload) {
        if (!payload) return;

        // 1. 低調狀態膠囊 (小圓點 + 即時同步)
        if (this.badge) {
            const dot = this.badge.querySelector(".status-dot") || document.createElement("span");
            const lbl = this.badge.querySelector(".status-label") || document.createElement("span");
            dot.className = "status-dot";
            lbl.className = "status-label";
            this.badge.innerHTML = "";
            this.badge.appendChild(dot);
            this.badge.appendChild(lbl);

            if (payload.status === "live") {
                this.badge.className = "queue-status-capsule";
                lbl.textContent = "即時同步";
                if (this.notice) this.notice.style.display = "none";
            } else if (payload.status === "cached") {
                this.badge.className = "queue-status-capsule cached";
                lbl.textContent = "前次快取";
                if (this.notice) {
                    this.notice.style.display = "block";
                    this.notice.style.background = "rgba(234, 179, 8, 0.1)";
                    this.notice.style.border = "1px solid rgba(234, 179, 8, 0.25)";
                    this.notice.style.color = "#FDE047";
                    this.notice.textContent = `⚠️ 連線異常，顯示前次有效快取 (${payload.error || "連線逾時"})`;
                }
            } else {
                this.badge.className = "queue-status-capsule empty";
                lbl.textContent = "尚未同步";
                if (this.notice) {
                    this.notice.style.display = "block";
                    this.notice.style.background = "rgba(248, 113, 113, 0.1)";
                    this.notice.style.border = "1px solid rgba(248, 113, 113, 0.25)";
                    this.notice.style.color = "#FCA5A5";
                    this.notice.textContent = `⚠️ ${payload.error || "等待同步雲端資料中..."}`;
                }
            }
        }

        // 2. 同步時間
        if (this.syncTime && payload.last_sync_time) {
            this.syncTime.textContent = `SYNC ${payload.last_sync_time}`;
        }

        // 3. 取得已報告組別 (過濾未報告，同組成員一起顯示)
        let groups = payload.groups || [];
        if (groups.length === 0 && payload.data && payload.data.length > 0) {
            const map = {};
            payload.data.forEach(item => {
                if (item.reported !== "已報告") return;
                const gid = item.group || 1;
                if (!map[gid]) {
                    map[gid] = {
                        group_id: gid,
                        group_name: `第 ${gid} 組`,
                        status: "已報告",
                        members: []
                    };
                }
                map[gid].members.push(item);
            });
            groups = Object.keys(map).sort((a,b)=>Number(a)-Number(b)).map(k => map[k]);
        }

        // 保存目前觀看中的組別 ID，局部更新時維持焦點
        const currentGroupId = (this.groups.length > 0 && this.groups[this.currentIndex - 1])
            ? this.groups[this.currentIndex - 1].group_id
            : null;

        this.groups = groups;
        this.clearTimer();

        // 4. 空狀態處理
        if (this.groups.length === 0) {
            this.track.innerHTML = `<div class="marquee-empty-hint">QUEUE EMPTY</div>`;
            this.track.style.transform = "none";
            this.track.style.transition = "none";
            this.updateIndicator();
            return;
        }

        // 5. 單組靜態處理 (不反覆移出再移入)
        if (this.groups.length === 1) {
            this.track.innerHTML = this.renderCardHtml(this.groups[0]);
            this.currentIndex = 1;
            this.track.style.transform = "none";
            this.track.style.transition = "none";
            this.applyTransform(false);
            this.updateIndicator();
            return;
        }

        // 6. 多組無縫循環結構構建: [clone_last, g0, g1, ..., clone_first]
        const lastGroup = this.groups[this.groups.length - 1];
        const firstGroup = this.groups[0];

        let trackHtml = "";
        trackHtml += this.renderCardHtml(lastGroup); // index 0 (clone of last)
        for (let i = 0; i < this.groups.length; i++) {
            trackHtml += this.renderCardHtml(this.groups[i]); // index 1 .. N
        }
        trackHtml += this.renderCardHtml(firstGroup); // index N+1 (clone of first)

        this.track.innerHTML = trackHtml;

        // 維持當前焦點組別
        if (currentGroupId !== null) {
            const foundIdx = this.groups.findIndex(g => g.group_id === currentGroupId);
            this.currentIndex = foundIdx !== -1 ? (foundIdx + 1) : 1;
        } else {
            this.currentIndex = 1;
        }

        // 立即對齊且無動畫跳躍
        this.applyTransform(false);
        this.updateIndicator();

        // 5 秒後推進下一組
        if (!this.isPaused) {
            this.scheduleNextStay();
        }
    }
}


let sheetsMarqueeCtrl = null;
function renderSheetsReport(res) {
    if (!sheetsMarqueeCtrl) {
        sheetsMarqueeCtrl = new VerticalMarqueeController();
    }
    sheetsMarqueeCtrl.updateData(res);
}

