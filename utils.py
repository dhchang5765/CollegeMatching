import json
import os
import re
from typing import Dict, Optional


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def extract_text(node):
    if not node:
        return ""
    return clean_text(node.get_text(" ", strip=True))


def load_json_db(path: str) -> Dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"JSON DB 파일이 없습니다: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
    
def normalize_subject(v: Optional[float]) -> float:
    if v is None:
        return 50.0
    if v <= 9:
        return max(0.0, 100 - (v - 1) * 12.5)
    return max(0.0, min(100.0, v))

def strip_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def normalize_major_name(s: str) -> str:
    s = strip_text(s).lower()
    s = s.replace("학과", "").replace("학부", "").replace("전공", "")
    s = s.replace(" ", "").replace("·", "").replace("-", "")
    return s