"""
FillinForm - Score Engine
嚴格遵循 build.md 第 4 章規範之跨平台分數換算引擎。
提供強防禦性數值清洗、邊界限制與精確向度權重換算。
"""

import math
from typing import Dict, List, Any, Union


def sanitize_score(val: Any, default: float = 80.0) -> float:
    """
    防禦性清洗輸入分數：
    拒絕 NaN, None, 非數值字串, 無限大，並強制 clamp 至 [1.0, 100.0]（最低分數為 1 分無 0 分）。
    """
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return max(1.0, min(100.0, f))
    except (ValueError, TypeError):
        return default


def round_half_up(val: float) -> int:
    """四捨五入 (Half-up)，與 JavaScript 的 Math.round 100% 一致"""
    return int(math.floor(val + 0.5))


def clamp(val: float, min_val: float, max_val: float) -> int:
    """Clamp and round float to nearest integer within [min_val, max_val]."""
    return int(max(min_val, min(max_val, round_half_up(val))))


class ScoreEngine:
    @staticmethod
    def calculate_all(
        topic: Union[float, int, Any],
        content: Union[float, int, Any],
        narrative: Union[float, int, Any],
        presentation: Union[float, int, Any],
        teamwork: Union[float, int, Any],
    ) -> Dict[str, Any]:
        """
        輸入五向度 T, C, N, P, W ∈ [0, 100]
        - S1 (0~5 級分): clamp(round(x/20), 0, 5)
        - S2/S3 (30/30/20/10/10 權重): T*0.3, C*0.3, N*0.2, P*0.1, W*0.1 各自 round 並 clamp
        - S4 (0~100 滑桿): 原值 clamp 至 [0, 100]
        - 加權總分 = round(T*0.3 + C*0.3 + N*0.2 + P*0.1 + W*0.1, 1)
        """
        t = sanitize_score(topic)
        c = sanitize_score(content)
        n = sanitize_score(narrative)
        p = sanitize_score(presentation)
        w = sanitize_score(teamwork)

        # 加權總分 (保留 1 位小數，與 JS Math.round(... * 10) / 10 一致)
        weighted_total = round_half_up((t * 0.30 + c * 0.30 + n * 0.20 + p * 0.10 + w * 0.10) * 10) / 10.0

        # S1: ChatGPT 互評站 (0~5 級分整數陣列)
        s1_scores: List[int] = [
            clamp(t / 20.0, 0, 5),
            clamp(c / 20.0, 0, 5),
            clamp(n / 20.0, 0, 5),
            clamp(p / 20.0, 0, 5),
            clamp(w / 20.0, 0, 5),
        ]

        # S2: Stanley Owen (30, 30, 20, 10, 10)
        s2_topic = clamp(t * 0.30, 0, 30)
        s2_content = clamp(c * 0.30, 0, 30)
        s2_narrative = clamp(n * 0.20, 0, 20)
        s2_presentation = clamp(p * 0.10, 0, 10)
        s2_teamwork = clamp(w * 0.10, 0, 10)
        s2_total = s2_topic + s2_content + s2_narrative + s2_presentation + s2_teamwork

        stanleyowen_scores = {
            "topicMastery": s2_topic,
            "contentRichness": s2_content,
            "narrativeSkill": s2_narrative,
            "presentationSkill": s2_presentation,
            "teamwork": s2_teamwork,
            "total": s2_total,
        }

        # S3: Google 表單 (30, 30, 20, 10, 10)
        googleform_scores = {
            "topic": s2_topic,
            "content": s2_content,
            "narrative": s2_narrative,
            "presentation": s2_presentation,
            "teamwork": s2_teamwork,
            "total": s2_total,
        }

        # S4: NLA (0~100 滑桿原值)
        nla_scores = {
            "score_topic": clamp(t, 0, 100),
            "score_content": clamp(c, 0, 100),
            "score_narrative": clamp(n, 0, 100),
            "score_presentation": clamp(p, 0, 100),
            "score_teamwork": clamp(w, 0, 100),
            "topic": clamp(t, 0, 100),
            "content": clamp(c, 0, 100),
            "narrative": clamp(n, 0, 100),
            "presentation": clamp(p, 0, 100),
            "teamwork": clamp(w, 0, 100),
            "weighted_total": weighted_total,
        }

        return {
            "clean_raw": {
                "topic": t,
                "content": c,
                "narrative": n,
                "presentation": p,
                "teamwork": w,
                "weighted_total": weighted_total,
            },
            "chatgpt": s1_scores,
            "stanleyowen": stanleyowen_scores,
            "googleform": googleform_scores,
            "nla": nla_scores,
        }
