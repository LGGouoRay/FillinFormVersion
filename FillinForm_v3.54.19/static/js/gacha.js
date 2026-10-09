/**
 * FillinForm - 評語建議卡池 (Gacha System)
 * 純靜態建議句庫，分 SSR / SR / R / N 四級僅作視覺趣味，不涉及任何分數偽裝。
 */

const GACHA_POOL = {
    SSR: [
        "報告架構極為嚴謹，論點切入深刻且具啟發性，簡報視覺與台風皆屬頂尖之作！",
        "深入淺出地剖析核心難題，數據論證扎實充分，團隊協作與臨場問答無懈可擊！",
        "題目選定具高度創新性，技術實現與實務價值兼具，聽完獲益良多，非常值得借鑑！"
    ],
    SR: [
        "內容詳實且邏輯清晰，投影片設計簡潔易懂，各組員分工默契極佳！",
        "報告者台風穩健、敘事流暢，能有效掌握聽眾注意力，整體完成度相當高。",
        "專案切入點明確，技術架構與實作成果皆有充分說明，具備良好實踐價值。"
    ],
    R: [
        "簡報節奏流暢，核心重點皆有傳達，若能在結論處加強未來展望會更加完整。",
        "內容充實，但部分投影片文字稍密，建議可適度以圖表輔助說明以增進可讀性。",
        "整體表現良好，口條清楚，題目選材切合課程主題，辛苦各位組員！"
    ],
    N: [
        "整體表現中規中矩，報告流程順暢，重點明確。",
        "台風沉穩，內容切題，團隊準備充分，辛苦了！",
        "報告清楚傳達專案進度與結果，整體中規中矩，表現合格。"
    ]
};

const GachaSystem = {
    draw() {
        const rand = Math.random();
        let tier = "N";
        if (rand < 0.10) {
            tier = "SSR";
        } else if (rand < 0.35) {
            tier = "SR";
        } else if (rand < 0.75) {
            tier = "R";
        } else {
            tier = "N";
        }

        const pool = GACHA_POOL[tier];
        const text = pool[Math.floor(Math.random() * pool.length)];

        return {
            tier: tier,
            text: text,
            color: tier === "SSR" ? "#FF75A0" : (tier === "SR" ? "#00F5D4" : (tier === "R" ? "#7928CA" : "#A0AEC0"))
        };
    }
};

window.GachaSystem = GachaSystem;
