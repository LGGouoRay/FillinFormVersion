/**
 * FillinForm - Frontend Score Engine
 * 與後端 core/score_engine.py 邏輯 100% 一致。
 */

function clamp(val, minVal, maxVal) {
    return Math.max(minVal, Math.min(maxVal, Math.round(val)));
}

function sanitizeScore(val, defaultVal = 80) {
    if (val === null || val === undefined) return defaultVal;
    const num = parseFloat(val);
    if (isNaN(num) || !isFinite(num)) return defaultVal;
    return Math.max(1, Math.min(100, num));
}

const ScoreEngine = {
    calculateAll(topic, content, narrative, presentation, teamwork) {
        const t = sanitizeScore(topic);
        const c = sanitizeScore(content);
        const n = sanitizeScore(narrative);
        const p = sanitizeScore(presentation);
        const w = sanitizeScore(teamwork);

        // 加權總分 (保留 1 位小數)
        const weightedTotal = Math.round((t * 0.30 + c * 0.30 + n * 0.20 + p * 0.10 + w * 0.10) * 10) / 10;

        // S1: 0~5 級分
        const s1Scores = [
            clamp(t / 20.0, 0, 5),
            clamp(c / 20.0, 0, 5),
            clamp(n / 20.0, 0, 5),
            clamp(p / 20.0, 0, 5),
            clamp(w / 20.0, 0, 5)
        ];

        // S2 / S3: 30, 30, 20, 10, 10
        const s2Topic = clamp(t * 0.30, 0, 30);
        const s2Content = clamp(c * 0.30, 0, 30);
        const s2Narrative = clamp(n * 0.20, 0, 20);
        const s2Presentation = clamp(p * 0.10, 0, 10);
        const s2Teamwork = clamp(w * 0.10, 0, 10);
        const s2Total = s2Topic + s2Content + s2Narrative + s2Presentation + s2Teamwork;

        const stanleyowenScores = {
            topicMastery: s2Topic,
            contentRichness: s2Content,
            narrativeSkill: s2Narrative,
            presentationSkill: s2Presentation,
            teamwork: s2Teamwork,
            total: s2Total
        };

        const googleformScores = {
            topic: s2Topic,
            content: s2Content,
            narrative: s2Narrative,
            presentation: s2Presentation,
            teamwork: s2Teamwork,
            total: s2Total
        };

        // S4: 0~100 滑桿原值
        const nlaScores = {
            score_topic: clamp(t, 0, 100),
            score_content: clamp(c, 0, 100),
            score_narrative: clamp(n, 0, 100),
            score_presentation: clamp(p, 0, 100),
            score_teamwork: clamp(w, 0, 100),
            topic: clamp(t, 0, 100),
            content: clamp(c, 0, 100),
            narrative: clamp(n, 0, 100),
            presentation: clamp(p, 0, 100),
            teamwork: clamp(w, 0, 100),
            weighted_total: weightedTotal
        };

        return {
            clean_raw: { topic: t, content: c, narrative: n, presentation: p, teamwork: w, weighted_total: weightedTotal },
            chatgpt: s1Scores,
            stanleyowen: stanleyowenScores,
            googleform: googleformScores,
            nla: nlaScores
        };
    }
};

window.ScoreEngine = ScoreEngine;
