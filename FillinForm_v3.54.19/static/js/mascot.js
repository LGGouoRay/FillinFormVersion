/**
 * FillinForm - 看板娘狀態機 (Mascot System)
 * 狀態機：IDLE / INPUT / DRYRUN / LAUNCH / SUCCESS / WARNING
 * 包含 SVG 眨眼動畫、表情切換與即時台詞對話泡泡。
 */

const MASCOT_DIALOGUES = {
    IDLE: [
        "你好呀！請選擇今天要評分的同學與組別～",
        "本機 Playwright 瀏覽器已經在後台待命囉！",
        "雙擊四等分畫面可以將真實網頁帶到最上層喔！"
    ],
    INPUT: [
        "正在調整向度分數嗎？我幫你即時算好四大平台數值！",
        "五向度滑桿會自動聯動換算～不用自己按計算機啦！",
        "寫不出評語嗎？試試看抽一張建議卡牌吧！"
    ],
    DRYRUN: [
        "🪄 演練模式已啟用！我們只填寫畫面，絕對不會偷送出～",
        "正在四個真實網頁中預填資料，請確認畫面是否正確！",
        "演練無誤後，再放心地點擊送出按鈕吧！"
    ],
    LAUNCH: [
        "🚀 準備送出！請在覆核視窗確認最後的送出明細喔！",
        "正在檢查所有防呆規則……自我互評：安全！組別：安全！",
        "確認無誤後，我會依序向勾選的平台提交！"
    ],
    SUCCESS: [
        "🎉 太棒了！評分已順利送出並記錄截圖證據！",
        "四平台同儕互評任務完成！辛苦啦～",
        "又搞定了一位同學！要繼續評下一位嗎？"
    ],
    WARNING: [
        "⚠️ 注意！偵測到可能的問題，請確認紅色警示訊息！",
        "不能給自己評分喔！這是自我互評防呆機制～",
        "若平台送出失敗，請點選該畫面手動登入或補填喔！"
    ]
};

class Mascot {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.currentState = "IDLE";
        this.bubbleTimeout = null;
        this.init();
    }

    init() {
        if (!this.container) return;
        this.renderSVG();
        this.setState("IDLE");
    }

    renderSVG() {
        this.container.innerHTML = `
            <div class="mascot-wrapper">
                <div class="mascot-bubble" id="mascotBubble">
                    <span id="mascotBubbleText">你好呀！請選擇今天要評分的同學～</span>
                </div>
                <div class="mascot-avatar" id="mascotAvatar">
                    <svg viewBox="0 0 120 120" class="mascot-svg" id="mascotSvg">
                        <defs>
                            <linearGradient id="hairGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" stop-color="#FF75A0" />
                                <stop offset="100%" stop-color="#7928CA" />
                            </linearGradient>
                            <linearGradient id="eyeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" stop-color="#00F5D4" />
                                <stop offset="100%" stop-color="#0099FF" />
                            </linearGradient>
                        </defs>
                        <!-- 頭部 -->
                        <circle cx="60" cy="60" r="42" fill="#FFE2D1" stroke="#333" stroke-width="2"/>
                        <!-- 頭髮 (背後) -->
                        <path d="M 22 55 C 10 90, 25 110, 35 115 C 30 95, 30 75, 35 60 Z" fill="url(#hairGrad)"/>
                        <path d="M 98 55 C 110 90, 95 110, 85 115 C 90 95, 90 75, 85 60 Z" fill="url(#hairGrad)"/>
                        <!-- 瀏海 -->
                        <path d="M 22 55 C 30 20, 90 20, 98 55 C 80 40, 75 42, 60 48 C 45 42, 40 40, 22 55 Z" fill="url(#hairGrad)"/>
                        <!-- 蝴蝶結 / 髮飾 -->
                        <polygon points="90,25 105,18 100,32" fill="#00F5D4"/>
                        <polygon points="90,25 105,32 100,18" fill="#00F5D4"/>
                        <circle cx="90" cy="25" r="3.5" fill="#FF75A0"/>
                        <!-- 左眼 -->
                        <g id="mascotLeftEye">
                            <ellipse cx="44" cy="62" rx="7" ry="9" fill="url(#eyeGrad)"/>
                            <ellipse cx="44" cy="62" rx="6" ry="8" fill="#1A202C"/>
                            <circle cx="42" cy="59" r="2.5" fill="#FFF"/>
                            <circle cx="46" cy="65" r="1.2" fill="#FFF"/>
                        </g>
                        <!-- 右眼 -->
                        <g id="mascotRightEye">
                            <ellipse cx="76" cy="62" rx="7" ry="9" fill="url(#eyeGrad)"/>
                            <ellipse cx="76" cy="62" rx="6" ry="8" fill="#1A202C"/>
                            <circle cx="74" cy="59" r="2.5" fill="#FFF"/>
                            <circle cx="78" cy="65" r="1.2" fill="#FFF"/>
                        </g>
                        <!-- 閉眼路徑 (眨眼用) -->
                        <path id="mascotClosedEyes" d="M 37 63 Q 44 68 51 63 M 69 63 Q 76 68 83 63" stroke="#2D3748" stroke-width="2.5" fill="none" stroke-linecap="round" style="display:none;"/>
                        <!-- 腮紅 -->
                        <ellipse cx="36" cy="72" rx="6" ry="3.5" fill="#FF75A0" opacity="0.6"/>
                        <ellipse cx="84" cy="72" rx="6" ry="3.5" fill="#FF75A0" opacity="0.6"/>
                        <!-- 嘴巴 (各狀態可切換) -->
                        <path id="mascotMouth" d="M 55 76 Q 60 82 65 76" stroke="#C53030" stroke-width="2" fill="none" stroke-linecap="round"/>
                    </svg>
                </div>
            </div>
        `;

        this.startBlinking();
    }

    startBlinking() {
        setInterval(() => {
            const leftEye = document.getElementById("mascotLeftEye");
            const rightEye = document.getElementById("mascotRightEye");
            const closedEyes = document.getElementById("mascotClosedEyes");
            if (leftEye && rightEye && closedEyes && this.currentState !== "WARNING") {
                leftEye.style.display = "none";
                rightEye.style.display = "none";
                closedEyes.style.display = "block";
                setTimeout(() => {
                    leftEye.style.display = "block";
                    rightEye.style.display = "block";
                    closedEyes.style.display = "none";
                }, 200);
            }
        }, 4000);
    }

    setState(state, customMessage = "") {
        this.currentState = state;
        const avatar = document.getElementById("mascotAvatar");
        const mouth = document.getElementById("mascotMouth");

        if (avatar) {
            avatar.className = `mascot-avatar state-${state.toLowerCase()}`;
        }

        if (mouth) {
            if (state === "SUCCESS") {
                mouth.setAttribute("d", "M 53 74 Q 60 85 67 74"); // 大笑
            } else if (state === "WARNING") {
                mouth.setAttribute("d", "M 55 79 Q 60 74 65 79"); // 難過/吃驚
            } else if (state === "DRYRUN") {
                mouth.setAttribute("d", "M 55 76 Q 60 79 65 76"); // 微笑
            } else {
                mouth.setAttribute("d", "M 55 76 Q 60 82 65 76"); // 一般
            }
        }

        let msg = customMessage;
        if (!msg) {
            const list = MASCOT_DIALOGUES[state] || MASCOT_DIALOGUES.IDLE;
            msg = list[Math.floor(Math.random() * list.length)];
        }
        this.speak(msg);
    }

    speak(text) {
        const bubbleText = document.getElementById("mascotBubbleText");
        const bubble = document.getElementById("mascotBubble");
        if (bubbleText && bubble) {
            bubbleText.innerText = text;
            bubble.classList.remove("pop");
            void bubble.offsetWidth; // trigger reflow
            bubble.classList.add("pop");
        }
    }
}

window.Mascot = Mascot;
