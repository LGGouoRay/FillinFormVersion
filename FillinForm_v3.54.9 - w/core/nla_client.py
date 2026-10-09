"""
FillinForm - S4 NLA Peer Review Client
(https://nla.ntust.org)
JWT-based Auth, Task Assignments & Grading Submission.
"""

from typing import Dict, Any, List, Optional
import requests


class NLAClient:
    BASE_URL = "https://nla.ntust.org"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        })
        self.token: Optional[str] = None

    def login(self, student_id: str, password: str) -> str:
        """
        Log in to NLA and obtain JWT Bearer token.
        POST /api/auth/login
        """
        url = f"{self.BASE_URL}/api/auth/login"
        payload = {
            "student_id": student_id.strip().upper(),
            "password": password,
        }
        resp = self.session.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        token = data.get("token") or data.get("access_token")
        if not token and isinstance(data.get("data"), dict):
            token = data["data"].get("token") or data["data"].get("access_token")

        if not token:
            raise ValueError(f"Failed to retrieve JWT token from NLA login response: {data}")

        self.token = token
        return token

    def get_my_assignments(self, task_id: str) -> List[Dict[str, Any]]:
        """
        Fetch the list of assigned peer reviews and student metadata.
        GET /api/tasks/{task_id}/my-assignments
        """
        if not self.token:
            raise ValueError("NLA client not authenticated. Please login first.")

        url = f"{self.BASE_URL}/api/tasks/{task_id}/my-assignments"
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = self.session.get(url, headers=headers, timeout=self.timeout)
        resp.raise_for_status()

        data = resp.json()
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return data.get("assignments") or data.get("data") or []
        return []

    def submit_review(
        self,
        assignment_id: str,
        scores: Dict[str, int],
        comment: str = "",
    ) -> Dict[str, Any]:
        """
        Submit rating scores and feedback for an assignment.
        POST /api/assignments/{assignment_id}/submit
        Payload:
        {
            "score_topic": int (0~100),
            "score_content": int (0~100),
            "score_narrative": int (0~100),
            "score_presentation": int (0~100),
            "score_teamwork": int (0~100),
            "comment": str
        }
        """
        if not self.token:
            raise ValueError("NLA client not authenticated. Please login first.")

        url = f"{self.BASE_URL}/api/assignments/{assignment_id}/submit"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        payload = {
            "score_topic": int(scores.get("score_topic", 0)),
            "score_content": int(scores.get("score_content", 0)),
            "score_narrative": int(scores.get("score_narrative", 0)),
            "score_presentation": int(scores.get("score_presentation", 0)),
            "score_teamwork": int(scores.get("score_teamwork", 0)),
            "comment": comment or "",
        }

        resp = self.session.post(url, headers=headers, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json() if resp.text else {"status": "success"}
