from typing import Dict, List
from bs4 import BeautifulSoup
from utils import *

def parse_report_html(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, "html.parser")
    return {
        "meta": extract_report_metadata(soup),
        "executive_summary": extract_executive_summary(soup),
        "diagnosis_sections": extract_diagnosis_sections(soup),
        "swot": extract_swot_section(soup),
        "simulation": extract_simulation_section(soup),
        "roadmap": extract_roadmap_section(soup),
        "final_conclusion": extract_final_conclusion(soup),
        "raw_text": clean_text(soup.get_text(" ", strip=True)),
    }

def extract_report_metadata(soup: BeautifulSoup) -> Dict:
    """표지(S01)와 Executive Summary(S02)에서 메타 정보를 추출."""
    meta = {
        "student_name": None,
        "report_date": None,
        "overall_score": None,
        "overall_grade": None,
        "total_pages": None,
    }

    # 표지 슬라이드
    cover = soup.select_one("div.slide.s01")
    if cover:
        # 날짜
        pre = cover.select_one(".s01-pretitle")
        if pre:
            meta["report_date"] = clean_text(pre.get_text())

        # 이름은 s01-h1 안에 student span이 있는 구조 (예시 기준)
        h1 = cover.select_one(".s01-h1")
        if h1:
            stu = h1.select_one(".stu")
            if stu:
                meta["student_name"] = clean_text(stu.get_text())

        # overall score / grade
        score_num = cover.select_one(".s01-score-num")
        score_grade = cover.select_one(".s01-score-grade")
        if score_num:
            try:
                meta["overall_score"] = float(clean_text(score_num.get_text()))
            except Exception:
                pass
        if score_grade:
            meta["overall_grade"] = clean_text(score_grade.get_text())

    # Executive summary 슬라이드에서 보정
    s02 = soup.select_one("div.slide.s02")
    if s02:
        # 날짜
        eyebrow = s02.select_one(".s02-eyebrow")
        if eyebrow and not meta["report_date"]:
            meta["report_date"] = clean_text(eyebrow.get_text())
        # 점수/등급
        h2 = s02.select_one(".s02-h2 span.gradeB, .s02-h2 span[class^='grade']")
        if h2:
            # e.g. "B 68 / 100" 형태라면 숫자/등급 파싱
            text = clean_text(h2.get_text())
            m = re.search(r"([A-F][\+\-]?)", text)
            if m and not meta["overall_grade"]:
                meta["overall_grade"] = m.group(1)
            m2 = re.search(r"(\d{1,3})\s*/\s*100", text)
            if m2 and not meta["overall_score"]:
                try:
                    meta["overall_score"] = float(m2.group(1))
                except Exception:
                    pass

    # 총 페이지 수 (하단 fbar의 pgnum 중 최대값)
    page_nums = []
    for span in soup.select(".fbar .pgnum"):
        t = clean_text(span.get_text())
        try:
            page_nums.append(int(t))
        except Exception:
            continue
    if page_nums:
        meta["total_pages"] = max(page_nums)

    return meta

def extract_executive_summary(soup: BeautifulSoup) -> Dict:
    """S02 EXECUTIVE SUMMARY 슬라이드 텍스트."""
    s02 = soup.select_one("div.slide.s02")
    if not s02:
        return {}
    body = s02.select_one(".s02-prose")
    return {
        "label": extract_text(s02.select_one(".s02-prose-label")),
        "text": extract_text(body),
    }

def extract_diagnosis_sections(soup: BeautifulSoup) -> List[Dict]:
    """DIAGNOSIS 01~10 슬라이드 정보를 리스트로 추출."""
    results = []
    for slide in soup.select("div.slide.dg"):
        eyebrow = slide.select_one(".dg-eyebrow")
        if not eyebrow:
            continue
        eyebrow_text = clean_text(eyebrow.get_text())
        if "DIAGNOSIS" not in eyebrow_text:
            # FAMILY CONTEXT 등 다른 dg 슬라이드는 제외
            continue

        # 번호, 문항 범위
        # e.g. "DIAGNOSIS 01 · 14 Q1~Q14"
        diag_no = None
        q_range = None
        m = re.search(r"DIAGNOSIS\s+(\d+)", eyebrow_text)
        if m:
            diag_no = int(m.group(1))
        m2 = re.search(r"(Q\d+[^ ]*)$", eyebrow_text)
        if m2:
            q_range = m2.group(1)

        title = extract_text(slide.select_one(".dg-h2"))
        banner_title = extract_text(slide.select_one(".dg-banner-title"))
        banner_tags = [clean_text(x.get_text()) for x in slide.select(".dg-banner-tag")]
        prose_label = extract_text(slide.select_one(".dg-prose-label"))
        prose_text = extract_text(slide.select_one(".dg-prose"))
        direct_quotes = [
            clean_text(line.get_text())
            for line in slide.select(".dg-quote-line")
        ]

        # 우측 카드들 (good/bad/warn/orange)
        cards = []
        for c in slide.select(".dg-cards .dg-card"):
            cls = " ".join(c.get("class", []))
            style_tag = "neutral"
            if "good" in cls:
                style_tag = "good"
            elif "bad" in cls:
                style_tag = "bad"
            elif "warn" in cls:
                style_tag = "warn"
            elif "orange" in cls:
                style_tag = "orange"
            cards.append({
                "style": style_tag,
                "label": extract_text(c.select_one(".dg-card-lbl")),
                "value": extract_text(c.select_one(".dg-card-val")),
                "desc": extract_text(c.select_one(".dg-card-desc")),
            })

        results.append({
            "diag_no": diag_no,
            "q_range": q_range,
            "title": title,
            "banner_title": banner_title,
            "banner_tags": banner_tags,
            "prose_label": prose_label,
            "prose_text": prose_text,
            "direct_quotes": direct_quotes,
            "cards": cards,
        })

    # diag_no 기준 정렬
    results.sort(key=lambda x: (x["diag_no"] if x["diag_no"] is not None else 999))
    return results

def extract_swot_section(soup: BeautifulSoup) -> Dict:
    """SWOT 4분면 슬라이드."""
    swot_slide = None
    for slide in soup.select("div.slide.dg, div.slide"):
        eyebrow = slide.select_one(".dg-eyebrow")
        if eyebrow and "INTEGRATED SWOT" in clean_text(eyebrow.get_text()):
            swot_slide = slide
            break
    if not swot_slide:
        return {}

    def _quad(letter: str) -> Dict:
        root = swot_slide.select_one(f".s13-quad.{letter}")
        if not root:
            return {}
        return {
            "title": extract_text(root.select_one(".s13-quad-title")),
            "sub": extract_text(root.select_one(".s13-quad-sub")),
            "items": [
                clean_text(li.get_text())
                for li in root.select(".s13-quad-list li")
            ],
        }

    return {
        "S": _quad("S"),
        "W": _quad("W"),
        "O": _quad("O"),
        "T": _quad("T"),
    }

def extract_simulation_section(soup: BeautifulSoup) -> Dict:
    """
    UNIVERSITY SIMULATION TIER MATRIX 또는 HIGH SCHOOL SIMULATION TIER MATRIX 섹션.
    """
    sim_slide = None
    for slide in soup.select("div.slide.dg"):
        eyebrow = slide.select_one(".dg-eyebrow")
        if not eyebrow:
            continue
        text = clean_text(eyebrow.get_text())
        if "SIMULATION TIER MATRIX" in text:
            sim_slide = slide
            break
    if not sim_slide:
        return {}

    banner_title = extract_text(sim_slide.select_one(".s15-banner-title"))
    stats = [
        clean_text(x.get_text())
        for x in sim_slide.select(".s15-banner-stat .num")
    ]

    tiers = []
    for univ in sim_slide.select(".s15-univs .s15-univ"):
        head = extract_text(univ.select_one(".s15-univ-head .tier"))
        name = extract_text(univ.select_one(".classname"))
        desc = extract_text(univ.select_one(".desc"))
        prob = extract_text(univ.select_one(".s15-univ-prob .pct"))
        tiers.append({
            "tier": head,
            "name": name,
            "desc": desc,
            "probability": prob,
        })

    return {
        "banner_title": banner_title,
        "stats": stats,
        "tiers": tiers,
    }

def extract_roadmap_section(soup: BeautifulSoup) -> Dict:
    """6-MONTH ACTION ROADMAP 슬라이드."""
    slide = None
    for s in soup.select("div.slide.dg"):
        eyebrow = s.select_one(".dg-eyebrow")
        if eyebrow and "6-MONTH ACTION ROADMAP" in clean_text(eyebrow.get_text()):
            slide = s
            break
    if not slide:
        return {}

    months = []
    for m in slide.select(".s16-month"):
        head = m.select_one(".s16-month-head")
        num = extract_text(head.select_one(".s16-month-num")) if head else ""
        tag = extract_text(head.select_one(".s16-month-tag")) if head else ""
        tasks = [
            clean_text(li.get_text())
            for li in m.select(".s16-month-tasks li")
        ]
        months.append({
            "label": f"{num} {tag}".strip(),
            "tasks": tasks,
        })

    return {
        "months": months,
    }

def extract_final_conclusion(soup: BeautifulSoup) -> Dict:
    """FINAL CONSULTANTS CONCLUSION 슬라이드."""
    slide = soup.select_one("div.slide.s17")
    if not slide:
        return {}
    title = extract_text(slide.select_one(".s17-pre"))
    cards = []
    for c in slide.select(".s17-card"):
        num = extract_text(c.select_one(".s17-card-num"))
        ctitle = extract_text(c.select_one(".s17-card-title"))
        body = extract_text(c.select_one(".s17-card-body"))
        cards.append({
            "num": num,
            "title": ctitle,
            "body": body,
        })
    bottom = extract_text(slide.select_one(".s17-final"))
    return {
        "title": title,
        "cards": cards,
        "bottom": bottom,
    }
