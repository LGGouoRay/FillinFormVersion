"""
FillinForm - S3 Google Form Client
(https://docs.google.com/forms/d/e/1FAIpQLSdHfP1Dbjt1CM0rd9Ecf-gpSO2Qvy7eApdC-yDvYM32greO_A)
優先動態解析受評者下拉選單，嚴格比對防呆，支援 HTTP POST /formResponse。
"""

import json
import re
from typing import Dict, Any, List, Optional
import requests

# 29 位同學於 Google 表單下拉選單之備援內建表
FALLBACK_OPTIONS = [
    "B10930022 游翔宇",
    "B11115002 徐巧芸",
    "B11115006 周重鈞",
    "B11115007 張凱森",
    "B11209015 連儷芳",
    "B11215025 魏晨名",
    "B11215027 葉宸宇",
    "B11215044 曾毓翔",
    "B11230223 葉家均",
    "B11230236 林碩斌",
    "B11315013 陳皓岳",
    "B11315015 張銘元",
    "B11315019 林聖傑",
    "B11315020 Santacitta Harris Islan",
    "B11315033 陳首宇",
    "B11315042 盧詠耀",
    "B11317033 邱千芷",
    "B11330201 蔣伊婷",
    "B11330217 賴韋宏",
    "B11330234 高俊傑",
    "B11330235 連紹傑",
    "B11332018 張家瑋",
    "B11415004 張仕鼎",
    "B11415006 秦翊竣",
    "B11415008 龔品誠",
    "B11415028 吳享叡",
    "B11415032 劉孟勛",
    "B11415042 陳昱霖",
    "B11415058 陳楷威"
]


class GoogleFormClient:
    FORM_ID = "1FAIpQLSdHfP1Dbjt1CM0rd9Ecf-gpSO2Qvy7eApdC-yDvYM32greO_A"
    VIEW_URL = f"https://docs.google.com/forms/d/e/{FORM_ID}/viewform"
    SUBMIT_URL = f"https://docs.google.com/forms/d/e/{FORM_ID}/formResponse"

    ENTRY_NAME = "entry.402598337"       # 填答者姓名
    ENTRY_STUDENT_ID = "entry.469913278" # 填答者學號
    ENTRY_TARGET = "entry.1255460099"    # 請選擇受評的報告者
    ENTRY_TOPIC = "entry.68362975"       # 主題掌握 (0~30)
    ENTRY_CONTENT = "entry.1936144904"   # 內容豐富 (0~30)
    ENTRY_NARRATIVE = "entry.2124525335" # 敘事技巧 (0~20)
    ENTRY_PRESENT = "entry.1259238831"   # 簡報技巧 (0~10)
    ENTRY_TEAM = "entry.757478034"       # 團隊表現 (0~10)
    ENTRY_COMMENT = "entry.2138219686"   # 具體回饋或建議

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
        self._cached_options: Optional[List[str]] = None

    def get_candidate_options(self, force_refresh: bool = False) -> List[str]:
        """
        從 Google 表單實際頁面動態解析受評者選項清單。
        解析失敗時回退內建備援表。
        """
        if self._cached_options and not force_refresh:
            return self._cached_options

        try:
            resp = self.session.get(self.VIEW_URL, timeout=self.timeout)
            resp.raise_for_status()
            match = re.search(r'var FB_PUBLIC_LOAD_DATA_\s*=\s*(.*?);</script>', resp.text, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                items = data[1][1]
                for item in items:
                    title = str(item[1]) + " " + str(item[2] if len(item) > 2 else "")
                    if "presenter" in title or "受評" in title:
                        if len(item) > 4 and item[4] and len(item[4]) > 0:
                            raw_opts = item[4][0][1]
                            options = [opt[0] for opt in raw_opts if opt and opt[0]]
                            if options:
                                self._cached_options = options
                                return self._cached_options
        except Exception:
            pass

        self._cached_options = list(FALLBACK_OPTIONS)
        return self._cached_options

    def match_target_option(self, target_student_id: str, target_name: str = "") -> str:
        """
        比對受評者下拉選單精確字串。
        遵循第 5 章規範：比對不上時必須停止提交並報錯，禁止模糊猜測送出。
        """
        options = self.get_candidate_options()
        cleaned_id = target_student_id.strip().upper()

        for opt in options:
            if cleaned_id in opt.upper():
                return opt

        if target_name:
            clean_name = target_name.strip()
            for opt in options:
                if clean_name and clean_name in opt:
                    return opt

        raise ValueError(
            f"【Google 表單名單比對失敗】無法在表單下拉選單中找到學生 [{target_student_id} {target_name}]，"
            f"已自動終止 S3 提交以防止資料錯誤！"
        )

    def submit_form(
        self,
        grader_name: str,
        grader_id: str,
        grader_email: str,
        target_option_text: str,
        scores: Dict[str, int],
        comment: str = "",
    ) -> bool:
        """
        提交同儕互評至 Google Form via formResponse POST。
        """
        payload = {
            self.ENTRY_NAME: grader_name,
            self.ENTRY_STUDENT_ID: grader_id,
            "emailAddress": grader_email,
            self.ENTRY_TARGET: target_option_text,
            self.ENTRY_TOPIC: str(scores.get("topic", 0)),
            self.ENTRY_CONTENT: str(scores.get("content", 0)),
            self.ENTRY_NARRATIVE: str(scores.get("narrative", 0)),
            self.ENTRY_PRESENT: str(scores.get("presentation", 0)),
            self.ENTRY_TEAM: str(scores.get("teamwork", 0)),
            self.ENTRY_COMMENT: comment or "",
            "fvv": "1",
            "pageHistory": "0",
        }

        resp = self.session.post(self.SUBMIT_URL, data=payload, timeout=self.timeout)
        if resp.status_code == 200:
            return True
        resp.raise_for_status()
        return True
