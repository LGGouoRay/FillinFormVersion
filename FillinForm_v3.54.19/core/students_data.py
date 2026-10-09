"""
FillinForm - Students Data & Safety Validation
附錄 B：29 位同學對照表與嚴格防呆規則。
"""

from typing import Dict, List, Any, Optional

STUDENTS: List[Dict[str, Any]] = [
    {"student_id": "B10930022", "name": "游翔宇", "group": 1},
    {"student_id": "B11115002", "name": "徐巧芸", "group": 1},
    {"student_id": "B11115006", "name": "周重鈞", "group": 1},
    {"student_id": "B11115007", "name": "張凱森", "group": 1},
    {"student_id": "B11209015", "name": "連儷芳", "group": 1},
    {"student_id": "B11215025", "name": "魏晨名", "group": 1},
    {"student_id": "B11215027", "name": "葉宸宇", "group": 1},
    {"student_id": "B11215044", "name": "曾毓翔", "group": 1},
    {"student_id": "B11230223", "name": "葉家均", "group": 1},
    {"student_id": "B11230236", "name": "林碩斌", "group": 1},
    {"student_id": "B11315013", "name": "陳皓岳", "group": 2},
    {"student_id": "B11315015", "name": "張銘元", "group": 2},
    {"student_id": "B11315019", "name": "林聖傑", "group": 2},
    {"student_id": "B11315020", "name": "Santacitta Harris Islan", "group": 2},
    {"student_id": "B11315033", "name": "陳首宇", "group": 2},
    {"student_id": "B11315042", "name": "盧詠耀", "group": 2},
    {"student_id": "B11317033", "name": "邱千芷", "group": 3},
    {"student_id": "B11330201", "name": "蔣伊婷", "group": 3},
    {"student_id": "B11330217", "name": "賴韋宏", "group": 3},
    {"student_id": "B11330234", "name": "高俊傑", "group": 3},
    {"student_id": "B11330235", "name": "連紹傑", "group": 3},
    {"student_id": "B11332018", "name": "張家瑋", "group": 3},
    {"student_id": "B11415004", "name": "張仕鼎", "group": 2},
    {"student_id": "B11415006", "name": "秦翊竣", "group": 2},
    {"student_id": "B11415008", "name": "龔品誠", "group": 2},
    {"student_id": "B11415028", "name": "吳享叡", "group": 3},
    {"student_id": "B11415032", "name": "劉孟勛", "group": 3},
    {"student_id": "B11415042", "name": "陳昱霖", "group": 3},
    {"student_id": "B11415058", "name": "陳楷威", "group": 3},
]

STUDENT_MAP: Dict[str, Dict[str, Any]] = {s["student_id"].upper(): s for s in STUDENTS}


def get_all_students() -> List[Dict[str, Any]]:
    """取得 29 位同學完整清單副本"""
    return [dict(s) for s in STUDENTS]


def get_student_by_id(student_id: str) -> Optional[Dict[str, Any]]:
    """依學號查詢學生資訊"""
    return STUDENT_MAP.get(student_id.strip().upper())


def validate_evaluation_target(target_id: str, reviewer_id: str) -> Dict[str, Any]:
    """
    評分對象合法性驗證：
    1. 允許自我互評（依使用者需求開放為自己評分）
    2. 目標學號必須存在於名單中
    """
    tid = target_id.strip().upper()
    rid = reviewer_id.strip().upper()

    target = get_student_by_id(tid)
    if not target:
        raise ValueError(f"【無效對象】受評學號 {tid} 不在班級互評 29 人名單中！")

    return target


def validate_group_bounds(group_num: int) -> int:
    """
    組別越界防呆：
    S1 與課程分組範圍為 1 ~ 50 組。
    """
    try:
        g = int(group_num)
    except (ValueError, TypeError):
        raise ValueError(f"【組別格式錯誤】組別必須為整數，得到：{group_num}")

    if g < 1 or g > 50:
        raise ValueError(f"【組別越界防呆】組別必須在 1 到 50 之間，得到：{g}")
    return g
