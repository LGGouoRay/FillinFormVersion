"""
FillinForm - S1 ChatGPT Peer Review Client
(https://class-peer-review-115-20261005.muddy-mite-0918.chatgpt.site)
"""

import requests
from typing import Dict, Any, List


class ChatGPTClient:
    BASE_URL = "https://class-peer-review-115-20261005.muddy-mite-0918.chatgpt.site"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    def get_student_info(self, student_id: str) -> Dict[str, Any]:
        """
        查詢學生資訊與已評組別清單。
        GET /api/student?id={student_id}
        """
        url = f"{self.BASE_URL}/api/student"
        resp = self.session.get(url, params={"id": student_id.strip().upper()}, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def submit_rating(self, student_id: str, group_num: int, scores: List[int]) -> Dict[str, Any]:
        """
        提交組別五項評分。
        POST /api/ratings
        Payload: {"id": student_id, "group": group_num, "scores": [s1, s2, s3, s4, s5]}
        """
        url = f"{self.BASE_URL}/api/ratings"
        payload = {
            "id": student_id.strip().upper(),
            "group": int(group_num),
            "scores": [int(s) for s in scores],
        }
        resp = self.session.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()
