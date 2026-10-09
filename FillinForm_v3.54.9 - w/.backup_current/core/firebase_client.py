"""
FillinForm - S2 Stanley Owen NTUST Grading Client
(https://ntust-grading.stanleyowen.com)
Backed by Google Firebase Auth & Cloud Firestore REST API.
"""

import datetime
from typing import Dict, Any, List, Optional
import requests


class FirebaseGradingClient:
    FIREBASE_API_KEY = "AIzaSyCeFhJuKTm0UTOncIjNJ3YbUIsvspI-p-A"
    PROJECT_ID = "ntust-grading"
    AUTH_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    FIRESTORE_URL = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.id_token: Optional[str] = None
        self.local_id: Optional[str] = None

    def login(self, email: str, password: str) -> Dict[str, Any]:
        """
        Authenticate using Firebase Identity Toolkit.
        """
        payload = {
            "email": email.strip(),
            "password": password,
            "returnSecureToken": True,
        }
        resp = self.session.post(self.AUTH_URL, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        self.id_token = data.get("idToken")
        self.local_id = data.get("localId")
        return data

    def get_students(self) -> List[Dict[str, Any]]:
        """
        List all students from Firestore 'students' collection.
        """
        if not self.id_token:
            raise ValueError("Firebase client not authenticated. Please login first.")

        headers = {"Authorization": f"Bearer {self.id_token}"}
        url = f"{self.FIRESTORE_URL}/students?pageSize=200"
        try:
            resp = self.session.get(url, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            docs = resp.json().get("documents", [])
            students = []
            for doc in docs:
                fields = doc.get("fields", {})
                student_id = fields.get("id", {}).get("stringValue", "") or doc.get("name", "").split("/")[-1]
                name = fields.get("name", {}).get("stringValue", "")
                group = fields.get("group", {}).get("integerValue", None)
                students.append({
                    "id": student_id,
                    "name": name,
                    "group": int(group) if group is not None else None,
                })
            return students
        except Exception:
            return []

    def submit_grade(
        self,
        grader_id: str,
        target_id: str,
        scores: Dict[str, int],
        comment: str = "",
        stage: str = "midterm",
    ) -> Dict[str, Any]:
        """
        Submit a peer grade to Firestore 'grades' collection.
        scores dict contains:
        topicMastery (0~30), contentRichness (0~30), narrativeSkill (0~20),
        presentationSkill (0~10), teamwork (0~10), total (0~100)
        """
        if not self.id_token:
            raise ValueError("Firebase client not authenticated. Please login first.")

        headers = {
            "Authorization": f"Bearer {self.id_token}",
            "Content-Type": "application/json",
        }
        url = f"{self.FIRESTORE_URL}/grades"
        now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        payload = {
            "fields": {
                "stage": {"stringValue": stage},
                "graderId": {"stringValue": grader_id},
                "targetId": {"stringValue": target_id},
                "scores": {
                    "mapValue": {
                        "fields": {
                            "topicMastery": {"integerValue": str(int(scores.get("topicMastery", 0)))},
                            "contentRichness": {"integerValue": str(int(scores.get("contentRichness", 0)))},
                            "narrativeSkill": {"integerValue": str(int(scores.get("narrativeSkill", 0)))},
                            "presentationSkill": {"integerValue": str(int(scores.get("presentationSkill", 0)))},
                            "teamwork": {"integerValue": str(int(scores.get("teamwork", 0)))},
                        }
                    }
                },
                "total": {"integerValue": str(int(scores.get("total", 0)))},
                "comment": {"stringValue": comment or ""},
                "timestamp": {"timestampValue": now_iso},
            }
        }

        resp = self.session.post(url, headers=headers, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()
