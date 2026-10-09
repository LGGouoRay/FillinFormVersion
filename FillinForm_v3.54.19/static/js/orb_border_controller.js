/**
 * FillinForm - Sakura Stream & Petals Drifting Border Controller
 * 櫻花流光環繞與花瓣飄落外框控制器
 * 
 * 規格遵守：
 * 1. 兩顆粉色光球分別由左上圓角弧線中點、右下圓角弧線中點啟動
 * 2. 順時針沿圓角外框中心線運行 (4s/圈，勻速 linear，首尾無縫銜接)
 * 3. 3 級光球層次 (5px 核心、10px 中光暈、24px 外擴散) 與 5.5% 周長彗星拖尾
 * 4. 【全新】櫻花流光與花瓣飄落：
 *    - 具備辨識度極高的小缺口櫻花花瓣 (非圓點、非愛心、非 emoji)
 *    - 色票：淺櫻粉 (#FFD9E8)、柔粉 (#FFB7D5)、主櫻粉 (#FF8FC4)、白粉高光 (#FFF3F8)
 *    - 僅在 filling 狀態生成，跟隨兩顆光球位置輕輕脫離 (流光帶起花瓣)
 *    - 單平台生成頻率：平均每秒 2~3 片 (兩球合計)，單平台上限 12 片，全畫面上限 32 片
 *    - 物理漂移：初始切線位移 -> 緩慢飄落 (18~45px) -> 左右搖曳 (8~24px) -> 旋轉 (30°~100°) -> 輕微 3D 飄浮翻轉
 *    - 存活週期：1.8~3.0s，前 15% 快速淡入，後 35% 漸進淡出
 * 5. 【全新】完成收尾 (櫻花散落)：
 *    - 平台進入 completed 時，播放一次小型收尾散落 (面板上緣左/右側釋出 6~8 片花瓣，向外向下散開)
 *    - 0.8~1.2s 內平滑淡出，雙光球與外框 450ms 淡出，最晚 1.2s 平台完全回歸乾淨 idle
 * 6. 錯誤與取消：立即停止生成，現有花瓣 200ms 快速淡出，不播放收尾散落
 * 7. 支援 ResizeObserver (85%/100%/115%、2x2、焦點放大、垂直雙欄動態貼合)
 * 8. 支援 prefers-reduced-motion: reduce (靜態粉色細框與靜態櫻花標誌，不播放流光與動態花瓣)
 * 9. pointer-events: none 獨立裝飾層，零版面侵入
 */

(function () {
    const ORB_CONFIG = {
        loopDuration: 4000,       // 每圈 4000ms, 勻速 linear
        fadeInDuration: 250,     // 250ms 淡入
        fadeOutDuration: 450,    // 450ms 淡出
        colors: {
            baseBorder: "#FF5EBA",
            baseAux: "#FF95D6",
            core: "#FFF0FA",
            midGlow: "#FF7BC8",
            outerGlow: "#FF4FAE"
        },
        coreRadius: 2.5,         // 直徑 5px
        midRadius: 6,
        outerRadius: 13,
        trailPercent: 0.055,     // 拖尾長度佔周長 5.5%
        borderRadius: 9.5        // 面板圓角中心線半徑
    };

    const SAKURA_CONFIG = {
        minInterval: 350,            // 平均 2~3 片/秒 (約 350~500ms 一片)
        maxInterval: 500,
        maxPanelPetals: 12,          // 單平台上限 10~14 片 (取 12)
        maxGlobalPetals: 32,         // 全畫面上限 32 片
        minLifetime: 1800,           // 1.8s
        maxLifetime: 3000,           // 3.0s
        sizeRange: [6.5, 11],        // 6.5~11px (基準 path 24px)
        completionScatterCount: 7,   // 收尾 6~8 片 (取 7)
        completionScatterDuration: 1000 // 0.8~1.2s (取 1.0s)
    };

    class OrbBorderManager {
        constructor() {
            this.sites = ["S1", "S2", "S3", "S4"];
            this.panels = {};
            this.rafId = null;
            this.isAnimating = false;
            this.resizeObserver = null;
            this.reducedMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        }

        init() {
            this.sites.forEach(siteId => {
                const panelEl = document.getElementById(`panel${siteId}`);
                if (!panelEl) return;

                // 建立獨立裝飾層 overlay
                let overlay = panelEl.querySelector(".orb-border-overlay");
                if (!overlay) {
                    overlay = document.createElement("div");
                    overlay.className = "orb-border-overlay";
                    overlay.setAttribute("aria-hidden", "true");
                    panelEl.appendChild(overlay);
                }

                // 建立 SVG 與元素結構
                overlay.innerHTML = this.buildSvgTemplate(siteId);

                this.panels[siteId] = {
                    panelEl: panelEl,
                    overlay: overlay,
                    svg: overlay.querySelector("svg"),
                    basePath: overlay.querySelector(".orb-base-path"),
                    // 拖尾組件 (3 層粗細與透明度重疊，形成如彗星般自然的流光拖尾)
                    trailA_outer: overlay.querySelector(".trail-a-outer"),
                    trailA_mid: overlay.querySelector(".trail-a-mid"),
                    trailA_inner: overlay.querySelector(".trail-a-inner"),
                    trailB_outer: overlay.querySelector(".trail-b-outer"),
                    trailB_mid: overlay.querySelector(".trail-b-mid"),
                    trailB_inner: overlay.querySelector(".trail-b-inner"),
                    orbGroupA: overlay.querySelector(".orb-group-a"),
                    orbGroupB: overlay.querySelector(".orb-group-b"),
                    // 櫻花花瓣粒子群組
                    sakuraGroup: overlay.querySelector(".sakura-petals-group"),
                    petals: [],          // 當前平台活動花瓣陣列
                    lastSpawnTime: 0,
                    nextSpawnInterval: 400,
                    spawnAlternate: false,
                    hasPlayedScatter: false,
                    state: "idle",       // idle, filling, completed, error
                    startTime: 0,
                    fadeOutTimer: null,
                    errorFadeTimer: null,
                    width: 0,
                    height: 0,
                    totalLength: 0,
                    startDistA: 0,
                    startDistB: 0
                };

                this.updatePanelGeometry(siteId);
            });

            // 監聽 ResizeObserver 以動態適應 85%/100%/115%、2x2/焦點/垂直雙欄、以及視窗變化
            if (window.ResizeObserver) {
                this.resizeObserver = new ResizeObserver((entries) => {
                    entries.forEach(entry => {
                        const targetId = entry.target.id;
                        const siteId = targetId.replace("panel", "");
                        if (this.panels[siteId]) {
                            this.updatePanelGeometry(siteId);
                        }
                    });
                });

                this.sites.forEach(siteId => {
                    const el = document.getElementById(`panel${siteId}`);
                    if (el) this.resizeObserver.observe(el);
                });
            }

            // 監聽無障礙減少動態媒體查詢變更
            if (window.matchMedia) {
                const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
                mq.addEventListener("change", (e) => {
                    this.reducedMotion = e.matches;
                    if (this.reducedMotion) {
                        this.sites.forEach(s => this.clearAllPetals(s));
                    }
                });
            }
        }

        buildSvgTemplate(siteId) {
            return `
                <svg class="orb-border-svg" id="orbSvg_${siteId}">
                    <defs>
                        <!-- 濾鏡：大範圍外部柔和光暈 (模糊約 20~28px) -->
                        <filter id="orbFilterOuter_${siteId}" x="-200%" y="-200%" width="500%" height="500%">
                            <feGaussianBlur in="SourceGraphic" stdDeviation="9" />
                        </filter>
                        <!-- 濾鏡：近距離亮粉色光暈 (模糊約 8~14px) -->
                        <filter id="orbFilterMid_${siteId}" x="-100%" y="-100%" width="300%" height="300%">
                            <feGaussianBlur in="SourceGraphic" stdDeviation="4" />
                        </filter>

                        <!-- 櫻花專用細微柔光濾鏡 (保持花瓣缺口銳利分明，不糊成粉點) -->
                        <filter id="sakuraGlow_${siteId}" x="-50%" y="-50%" width="200%" height="200%">
                            <feDropShadow dx="0" dy="0.8" stdDeviation="0.8" flood-color="#FF7BC8" flood-opacity="0.32" />
                        </filter>

                        <!-- 櫻花花瓣母版路徑：標準 20x24 寬端帶有辨識度極高的櫻花小凹口 (Notch) -->
                        <path id="sakuraPetalMaster_${siteId}"
                              d="M 10 23.5 C 5.8 19.8, 1.8 13.5, 1.8 8.2 C 1.8 3.6, 6.2 1.2, 8.6 3.2 C 9.3 3.8, 9.7 4.8, 10 4.8 C 10.3 4.8, 10.7 3.8, 11.4 3.0 C 13.8 0.9, 18.2 3.2, 18.2 8.2 C 18.2 13.5, 14.2 19.8, 10 23.5 Z" />

                        <!-- 櫻花漸層 1: 柔美主櫻粉 (#FFF3F8 高光 -> #FFD9E8 -> #FFB7D5 -> #FF8FC4) -->
                        <linearGradient id="sakuraGrad_${siteId}_1" x1="20%" y1="0%" x2="80%" y2="100%">
                            <stop offset="0%" stop-color="#FFF3F8" stop-opacity="0.95" />
                            <stop offset="35%" stop-color="#FFD9E8" stop-opacity="0.92" />
                            <stop offset="70%" stop-color="#FFB7D5" stop-opacity="0.90" />
                            <stop offset="100%" stop-color="#FF8FC4" stop-opacity="0.95" />
                        </linearGradient>

                        <!-- 櫻花漸層 2: 淺櫻粉通透 (#FFB7D5 -> #FFD9E8 -> #FFF3F8) -->
                        <linearGradient id="sakuraGrad_${siteId}_2" x1="0%" y1="100%" x2="100%" y2="0%">
                            <stop offset="0%" stop-color="#FFB7D5" stop-opacity="0.88" />
                            <stop offset="40%" stop-color="#FFD9E8" stop-opacity="0.92" />
                            <stop offset="100%" stop-color="#FFF3F8" stop-opacity="0.98" />
                        </linearGradient>

                        <!-- 櫻花漸層 3: 鮮明櫻粉 (高光 -> 柔粉 -> 主櫻粉深色) -->
                        <linearGradient id="sakuraGrad_${siteId}_3" x1="50%" y1="0%" x2="50%" y2="100%">
                            <stop offset="0%" stop-color="#FFF3F8" stop-opacity="0.95" />
                            <stop offset="45%" stop-color="#FFB7D5" stop-opacity="0.90" />
                            <stop offset="100%" stop-color="#FF72B4" stop-opacity="0.94" />
                        </linearGradient>
                    </defs>

                    <!-- 基本外框粉色霓虹輪廓 -->
                    <path class="orb-base-path" />

                    <!-- 光球 A 拖尾 (3 層梯度重疊) -->
                    <path class="orb-trail-path trail-a-outer" stroke="${ORB_CONFIG.colors.outerGlow}" stroke-width="1.8" opacity="0.30" />
                    <path class="orb-trail-path trail-a-mid" stroke="${ORB_CONFIG.colors.midGlow}" stroke-width="2.2" opacity="0.60" />
                    <path class="orb-trail-path trail-a-inner" stroke="${ORB_CONFIG.colors.baseAux}" stroke-width="2.6" opacity="0.95" />

                    <!-- 光球 B 拖尾 (3 層梯度重疊) -->
                    <path class="orb-trail-path trail-b-outer" stroke="${ORB_CONFIG.colors.outerGlow}" stroke-width="1.8" opacity="0.30" />
                    <path class="orb-trail-path trail-b-mid" stroke="${ORB_CONFIG.colors.midGlow}" stroke-width="2.2" opacity="0.60" />
                    <path class="orb-trail-path trail-b-inner" stroke="${ORB_CONFIG.colors.baseAux}" stroke-width="2.6" opacity="0.95" />

                    <!-- 光球 A (左上圓角中點啟動) -->
                    <g class="orb-group orb-group-a orb-a">
                        <!-- 第 3 層：大範圍外部光暈 -->
                        <circle r="${ORB_CONFIG.outerRadius}" fill="${ORB_CONFIG.colors.outerGlow}" opacity="0.45" filter="url(#orbFilterOuter_${siteId})" />
                        <!-- 第 2 層：近距離粉色光暈 -->
                        <circle r="${ORB_CONFIG.midRadius}" fill="${ORB_CONFIG.colors.midGlow}" opacity="0.85" filter="url(#orbFilterMid_${siteId})" />
                        <!-- 第 1 層：明亮核心 -->
                        <circle r="${ORB_CONFIG.coreRadius}" fill="${ORB_CONFIG.colors.core}" />
                    </g>

                    <!-- 光球 B (右下圓角中點啟動，相距 50% 周長) -->
                    <g class="orb-group orb-group-b orb-b">
                        <circle r="${ORB_CONFIG.outerRadius}" fill="${ORB_CONFIG.colors.outerGlow}" opacity="0.45" filter="url(#orbFilterOuter_${siteId})" />
                        <circle r="${ORB_CONFIG.midRadius}" fill="${ORB_CONFIG.colors.midGlow}" opacity="0.85" filter="url(#orbFilterMid_${siteId})" />
                        <circle r="${ORB_CONFIG.coreRadius}" fill="${ORB_CONFIG.colors.core}" />
                    </g>

                    <!-- 櫻花花瓣粒子圖層 (置於最上層，半透明浮動) -->
                    <g class="sakura-petals-group" id="sakuraGroup_${siteId}"></g>

                    <!-- 無障礙模式專用：右上角微型靜態櫻花標誌 -->
                    <g class="sakura-reduced-motion-icon" display="none">
                        <use href="#sakuraPetalMaster_${siteId}" fill="url(#sakuraGrad_${siteId}_1)" transform="translate(18, 14) scale(0.42) translate(-10, -12)" />
                    </g>
                </svg>
            `;
        }

        updatePanelGeometry(siteId) {
            const p = this.panels[siteId];
            if (!p) return;

            const rect = p.panelEl.getBoundingClientRect();
            const w = rect.width;
            const h = rect.height;
            if (w <= 0 || h <= 0) return;

            p.width = w;
            p.height = h;

            p.svg.setAttribute("viewBox", `0 0 ${w} ${h}`);

            // 面板邊框中心線幾何 (stroke 居中在邊框上，內縮 0.5px)
            const r = ORB_CONFIG.borderRadius;
            const x = 0.5;
            const y = 0.5;
            const bw = Math.max(1, w - 1);
            const bh = Math.max(1, h - 1);

            // 圓角矩形順時針路徑：
            // 起點 (x+r, y) -> 上邊右行 -> 右上圓角 -> 右邊下行 -> 右下圓角 -> 下邊左行 -> 左下圓角 -> 左邊上行 -> 左上圓角 -> 封閉 Z
            const d = `M ${x + r} ${y} ` +
                      `H ${x + bw - r} ` +
                      `A ${r} ${r} 0 0 1 ${x + bw} ${y + r} ` +
                      `V ${y + bh - r} ` +
                      `A ${r} ${r} 0 0 1 ${x + bw - r} ${y + bh} ` +
                      `H ${x + r} ` +
                      `A ${r} ${r} 0 0 1 ${x} ${y + bh - r} ` +
                      `V ${y + r} ` +
                      `A ${r} ${r} 0 0 1 ${x + r} ${y} Z`;

            p.basePath.setAttribute("d", d);
            p.trailA_outer.setAttribute("d", d);
            p.trailA_mid.setAttribute("d", d);
            p.trailA_inner.setAttribute("d", d);
            p.trailB_outer.setAttribute("d", d);
            p.trailB_mid.setAttribute("d", d);
            p.trailB_inner.setAttribute("d", d);

            const L = p.basePath.getTotalLength();
            p.totalLength = L;

            // 弧長中點計算：
            // 左上角弧線長度為 (PI * r / 2)，在路徑末端銜接處。其中點距離為 L - (PI * r / 4)
            p.startDistA = L - (Math.PI * r / 4);
            // 右下角弧線中點正好相距 50% 周長 (L / 2)
            p.startDistB = (p.startDistA + 0.5 * L) % L;

            // 初始靜態位置更新一次
            this.renderFrame(performance.now(), siteId);
        }

        setSiteState(siteId, newState) {
            const p = this.panels[siteId];
            if (!p) return;

            const now = performance.now();

            if (newState === "filling") {
                if (p.fadeOutTimer) {
                    clearTimeout(p.fadeOutTimer);
                    p.fadeOutTimer = null;
                }
                if (p.errorFadeTimer) {
                    clearTimeout(p.errorFadeTimer);
                    p.errorFadeTimer = null;
                }

                if (p.state !== "filling") {
                    p.state = "filling";
                    p.startTime = now;
                    p.lastSpawnTime = now;
                    p.nextSpawnInterval = 380;
                    p.hasPlayedScatter = false;
                }

                p.overlay.classList.add("is-filling");
                p.overlay.classList.remove("is-fading-out");
                p.overlay.style.transition = `opacity ${ORB_CONFIG.fadeInDuration}ms ease`;
                p.overlay.style.opacity = "1";

                if (p.sakuraGroup) {
                    p.sakuraGroup.style.transition = "";
                    p.sakuraGroup.style.opacity = "1";
                }

                if (!this.reducedMotion) {
                    this.startAnimationLoop();
                }
            } else if (newState === "completed") {
                if (p.state !== "filling") return;

                p.state = "completed";

                // 1. 播放一次小型櫻花散落收尾 (6~8 片花瓣自上緣輕盈向外散開)
                if (!this.reducedMotion && !p.hasPlayedScatter) {
                    p.hasPlayedScatter = true;
                    this.playCompletionScatter(siteId, now);
                }

                // 2. 粉色外框與雙光球在 450ms 內柔和淡出
                p.overlay.classList.add("is-fading-out");
                p.overlay.style.transition = `opacity ${ORB_CONFIG.fadeOutDuration}ms ease`;
                p.overlay.style.opacity = "0";

                // 3. 最晚 1.2s 後，徹底清除殘留並恢復 idle
                p.fadeOutTimer = setTimeout(() => {
                    if (p.state === "completed") {
                        p.state = "idle";
                        p.overlay.classList.remove("is-filling", "is-fading-out");
                        this.clearAllPetals(siteId);
                        this.checkIfAnimationCanStop();
                    }
                }, 1200);
            } else if (newState === "error" || newState === "idle") {
                if (p.fadeOutTimer) {
                    clearTimeout(p.fadeOutTimer);
                    p.fadeOutTimer = null;
                }

                p.state = "idle";
                p.overlay.classList.remove("is-filling");
                p.overlay.style.transition = "opacity 200ms ease";
                p.overlay.style.opacity = "0";

                // 現有花瓣在 200~250ms 內快速淡出，不播放完成散落
                if (p.sakuraGroup) {
                    p.sakuraGroup.style.transition = "opacity 200ms ease";
                    p.sakuraGroup.style.opacity = "0";
                }

                p.errorFadeTimer = setTimeout(() => {
                    this.clearAllPetals(siteId);
                    this.checkIfAnimationCanStop();
                }, 220);
            }
        }

        startAnimationLoop() {
            if (this.isAnimating) return;
            this.isAnimating = true;

            const tick = (now) => {
                let hasActive = false;
                this.sites.forEach(siteId => {
                    const p = this.panels[siteId];
                    if (p && (p.state === "filling" || p.state === "completed" || p.petals.length > 0)) {
                        hasActive = true;
                        this.renderFrame(now, siteId);
                    }
                });

                if (hasActive) {
                    this.rafId = requestAnimationFrame(tick);
                } else {
                    this.isAnimating = false;
                    this.rafId = null;
                }
            };

            this.rafId = requestAnimationFrame(tick);
        }

        checkIfAnimationCanStop() {
            const anyActive = this.sites.some(s => {
                const p = this.panels[s];
                return p && (p.state === "filling" || p.state === "completed" || p.petals.length > 0);
            });
            if (!anyActive && this.rafId) {
                cancelAnimationFrame(this.rafId);
                this.rafId = null;
                this.isAnimating = false;
            }
        }

        getTotalActivePetals() {
            let count = 0;
            this.sites.forEach(s => {
                const p = this.panels[s];
                if (p && p.petals) count += p.petals.length;
            });
            return count;
        }

        renderFrame(now, siteId) {
            const p = this.panels[siteId];
            if (!p || p.totalLength <= 0) return;

            const L = p.totalLength;
            const elapsed = Math.max(0, now - (p.startTime || now));
            const progress = (elapsed % ORB_CONFIG.loopDuration) / ORB_CONFIG.loopDuration; // [0, 1)

            // 雙光球當前路徑距離 (順時針等速前進)
            const distA = (p.startDistA + progress * L) % L;
            const distB = (p.startDistB + progress * L) % L;

            // 透過 SVG getPointAtLength 精準取得 sub-pixel 座標
            const ptA = p.basePath.getPointAtLength(distA);
            const ptB = p.basePath.getPointAtLength(distB);

            // 更新光球位置
            p.orbGroupA.setAttribute("transform", `translate(${ptA.x}, ${ptA.y})`);
            p.orbGroupB.setAttribute("transform", `translate(${ptB.y !== undefined ? ptB.x : ptA.x}, ${ptB.y !== undefined ? ptB.y : ptA.y})`);

            // 更新短流光拖尾 (長度約 5.5% 周長)
            const tl = L * ORB_CONFIG.trailPercent;

            this.updateTrailPath(p.trailA_outer, L, tl, distA);
            this.updateTrailPath(p.trailA_mid, L, tl * 0.65, distA);
            this.updateTrailPath(p.trailA_inner, L, tl * 0.30, distA);

            this.updateTrailPath(p.trailB_outer, L, tl, distB);
            this.updateTrailPath(p.trailB_mid, L, tl * 0.65, distB);
            this.updateTrailPath(p.trailB_inner, L, tl * 0.30, distB);

            // ==================== 櫻花花瓣生成與物理運動 ====================
            if (!this.reducedMotion) {
                // 1. filling 狀態跟隨光球動態生成櫻花
                if (p.state === "filling") {
                    if (now - p.lastSpawnTime >= p.nextSpawnInterval) {
                        const globalCount = this.getTotalActivePetals();
                        if (p.petals.length < SAKURA_CONFIG.maxPanelPetals && globalCount < SAKURA_CONFIG.maxGlobalPetals) {
                            // 兩顆光球輪流脫離出花瓣
                            p.spawnAlternate = !p.spawnAlternate;
                            const sourceDist = p.spawnAlternate ? distA : distB;
                            const sourcePt = p.spawnAlternate ? ptA : ptB;

                            // 估算切線運動向量 (前 4px 與當前差值)
                            const prevDist = (sourceDist - 4 + L) % L;
                            const prevPt = p.basePath.getPointAtLength(prevDist);
                            const tanX = sourcePt.x - prevPt.x;
                            const tanY = sourcePt.y - prevPt.y;

                            this.spawnPetal(siteId, sourcePt, { x: tanX, y: tanY }, now);
                        }
                        p.lastSpawnTime = now;
                        p.nextSpawnInterval = SAKURA_CONFIG.minInterval + Math.random() * (SAKURA_CONFIG.maxInterval - SAKURA_CONFIG.minInterval);
                    }
                }

                // 2. 更新所有活動花瓣位置、旋轉、3D 飄動與漸隱
                this.updatePetals(p, now);
            }
        }

        spawnPetal(siteId, pt, tan, now, isScatter = false) {
            const p = this.panels[siteId];
            if (!p || !p.sakuraGroup) return;

            // 計算單位切線方向
            const mag = Math.hypot(tan.x, tan.y) || 1;
            const ux = tan.x / mag;
            const uy = tan.y / mag;

            // 初始座標：微偏向光球後方，隨機小幅抖動
            const x0 = pt.x - ux * (2 + Math.random() * 5) + (Math.random() - 0.5) * 4;
            const y0 = pt.y - uy * (2 + Math.random() * 5) + (Math.random() - 0.5) * 4;

            // 初始流光速度 (向前衝出小段後被重力與空氣阻尼捕捉)
            const initSpeed = isScatter ? (15 + Math.random() * 20) : (8 + Math.random() * 12);
            const initVx = ux * initSpeed + (Math.random() - 0.5) * 6;
            const initVy = uy * initSpeed + (Math.random() - 0.5) * 6;

            // 尺寸：5~10px (偶爾至 12px)
            const size = isScatter ? (6 + Math.random() * 4) : (SAKURA_CONFIG.sizeRange[0] + Math.random() * (SAKURA_CONFIG.sizeRange[1] - SAKURA_CONFIG.sizeRange[0]));
            const scale = size / 24; // 基準 SVG 寬 20 高 24

            // 存活週期
            const duration = isScatter ?
                (800 + Math.random() * 350) :
                (SAKURA_CONFIG.minLifetime + Math.random() * (SAKURA_CONFIG.maxLifetime - SAKURA_CONFIG.minLifetime));

            // 隨機選取 1~3 種柔粉漸層
            const gradNum = Math.floor(Math.random() * 3) + 1;

            // 建立花瓣 SVG DOM 節點
            const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
            g.className.baseVal = "sakura-petal";
            g.style.pointerEvents = "none";
            g.style.opacity = "0";

            const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
            use.setAttribute("href", `#sakuraPetalMaster_${siteId}`);
            use.setAttribute("fill", `url(#sakuraGrad_${siteId}_${gradNum})`);
            use.setAttribute("filter", `url(#sakuraGlow_${siteId})`);
            use.setAttribute("stroke", "rgba(255, 255, 255, 0.40)");
            use.setAttribute("stroke-width", "0.35");
            g.appendChild(use);

            p.sakuraGroup.appendChild(g);

            const petalObj = {
                el: g,
                x0: x0,
                y0: y0,
                vx: initVx,
                vy: initVy,
                driftX: (Math.random() - 0.5) * (isScatter ? 28 : 16),
                swayAmp: 4 + Math.random() * 7,
                swayFreq: 2.0 + Math.random() * 1.6,
                swayPhase: Math.random() * Math.PI * 2,
                fallSpeed: isScatter ? (18 + Math.random() * 15) : (10 + Math.random() * 10), // px/s
                rot0: Math.random() * 360,
                rotSpeed: (Math.random() < 0.5 ? 1 : -1) * (25 + Math.random() * 35),
                flutterFreq: 3.2 + Math.random() * 2.8,
                flutterPhase: Math.random() * Math.PI * 2,
                scale: scale,
                maxOpacity: 0.88 + Math.random() * 0.10,
                birthTime: now,
                duration: duration
            };

            p.petals.push(petalObj);
        }

        updatePetals(p, now) {
            for (let i = p.petals.length - 1; i >= 0; i--) {
                const pet = p.petals[i];
                const age = now - pet.birthTime;

                if (age >= pet.duration) {
                    pet.el.remove();
                    p.petals.splice(i, 1);
                    continue;
                }

                const progress = age / pet.duration;
                const sec = age / 1000;

                // 初始衝量在 0.4 秒內被阻尼吸收
                const damp = Math.exp(-sec * 2.8);
                const currX = pet.x0 + pet.vx * sec * damp + pet.driftX * progress + pet.swayAmp * Math.sin(sec * pet.swayFreq + pet.swayPhase);
                const currY = pet.y0 + pet.vy * sec * damp + pet.fallSpeed * sec;

                // 旋轉與 3D 飄浮 (flipX 輕微在 0.78~1.0 之間律動，營造花瓣翻動飄拂感)
                const currRot = pet.rot0 + pet.rotSpeed * sec;
                const flipX = pet.scale * (0.80 + 0.20 * Math.cos(sec * pet.flutterFreq + pet.flutterPhase));
                const flipY = pet.scale;

                // 透明度曲線：前 15% 柔和淡入，中段保持，後 35% 漸進淡出
                let op = pet.maxOpacity;
                if (progress < 0.15) {
                    op = pet.maxOpacity * (progress / 0.15);
                } else if (progress > 0.65) {
                    op = pet.maxOpacity * (1 - (progress - 0.65) / 0.35);
                }

                // 設置座標與縮放 (中心點對準基準路徑中心 10, 12)
                pet.el.setAttribute("transform", `translate(${currX}, ${currY}) rotate(${currRot}) scale(${flipX}, ${flipY}) translate(-10, -12)`);
                pet.el.style.opacity = Math.max(0, Math.min(1, op)).toFixed(3);
            }
        }

        playCompletionScatter(siteId, now) {
            const p = this.panels[siteId];
            if (!p || p.width <= 0) return;

            const w = p.width;
            const count = SAKURA_CONFIG.completionScatterCount; // 7 片

            // 左側 3 片，自左上緣向左下散開
            const leftCount = Math.floor(count / 2); // 3
            for (let i = 0; i < leftCount; i++) {
                const x = w * (0.12 + Math.random() * 0.14);
                const y = 4 + Math.random() * 8;
                const tan = { x: -1.0, y: 0.5 + Math.random() * 0.5 };
                this.spawnPetal(siteId, { x, y }, tan, now, true);
            }

            // 右側 4 片，自右上緣向右下散開
            const rightCount = count - leftCount; // 4
            for (let i = 0; i < rightCount; i++) {
                const x = w * (0.74 + Math.random() * 0.14);
                const y = 4 + Math.random() * 8;
                const tan = { x: 1.0, y: 0.5 + Math.random() * 0.5 };
                this.spawnPetal(siteId, { x, y }, tan, now, true);
            }
        }

        clearAllPetals(siteId) {
            const p = this.panels[siteId];
            if (!p) return;
            p.petals.forEach(pet => {
                if (pet.el && pet.el.parentNode) {
                    pet.el.parentNode.removeChild(pet.el);
                }
            });
            p.petals = [];
            if (p.sakuraGroup) {
                p.sakuraGroup.innerHTML = "";
                p.sakuraGroup.style.opacity = "1";
            }
        }

        updateTrailPath(pathEl, totalL, trailLen, headDist) {
            pathEl.setAttribute("stroke-dasharray", `${trailLen} ${Math.max(1, totalL - trailLen)}`);
            pathEl.setAttribute("stroke-dashoffset", `${-(headDist - trailLen)}`);
        }

        resetAll() {
            this.sites.forEach(s => this.setSiteState(s, "idle"));
        }
    }

    // 掛載至全域
    window.OrbBorderController = new OrbBorderManager();
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => {
            window.OrbBorderController.init();
        });
    } else {
        window.OrbBorderController.init();
    }
})();
