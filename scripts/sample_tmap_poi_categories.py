"""
TMAP POI 검색 API로 업종(카테고리) 필드 샘플 수집.

Usage:
    python scripts/sample_tmap_poi_categories.py
    python scripts/sample_tmap_poi_categories.py --out data/tmap_poi_category_samples.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

CATEGORY_FIELDS = (
    "upperBizName",
    "middleBizName",
    "lowerBizName",
    "bizName",
    "className",
    "upperClassName",
    "middleClassName",
    "lowerClassName",
    "classCode",
    "bizCode",
)

# 다양한 업종·장소 유형을 넓게 샘플링
SAMPLE_KEYWORDS = [
    "스타벅스",
    "맥도날드",
    "경복궁",
    "국립중앙박물관",
    "롯데백화점",
    "이마트",
    "해운대해수욕장",
    "부산역",
    "CGV",
    "올리브영",
    "병원",
    "약국",
    "호텔",
    "펜션",
    "주유소",
    "공영주차장",
    "한강공원",
    "카페",
    "맛집",
    "관광지",
    "전통시장",
    "놀이공원",
    "대학교",
    "교회",
    "헬스장",
    "미용실",
    "은행",
    "우체국",
    "편의점",
    "GS25",
    "던킨도너츠",
    "교보문고",
    "노래방",
    "찜질방",
    "아울렛",
    "벡스코",
    "광안리",
    "자갈치시장",
    "태종대",
    "감천문화마을",
]


def fetch_pois(keyword: str, count: int = 5) -> list[dict]:
    key = os.getenv("TMAP_APP_KEY", "").strip()
    if not key:
        raise SystemExit("TMAP_APP_KEY가 .env에 없습니다.")

    resp = requests.get(
        "https://apis.openapi.sk.com/tmap/pois",
        params={
            "version": "1",
            "searchKeyword": keyword.strip(),
            "count": count,
            "reqCoordType": "WGS84GEO",
            "resCoordType": "WGS84GEO",
        },
        headers={"appKey": key, "Accept": "application/json"},
        timeout=15,
    )
    if resp.status_code != 200:
        return []

    pois = resp.json().get("searchPoiInfo", {}).get("pois", {}).get("poi", [])
    if isinstance(pois, dict):
        pois = [pois]
    return pois or []


def extract_category_row(poi: dict, keyword: str) -> dict:
    row = {"search_keyword": keyword, "name": poi.get("name") or ""}
    for field in CATEGORY_FIELDS:
        val = poi.get(field)
        if val not in (None, ""):
            row[field] = val
    return row


def build_summary(rows: list[dict]) -> dict:
    upper = Counter()
    middle = Counter()
    lower = Counter()
    triples: dict[tuple[str, str, str], int] = Counter()

    for row in rows:
        u = row.get("upperBizName", "")
        m = row.get("middleBizName", "")
        l = row.get("lowerBizName", "")
        if u:
            upper[u] += 1
        if m:
            middle[m] += 1
        if l:
            lower[l] += 1
        if u or m or l:
            triples[(u, m, l)] += 1

    return {
        "total_pois": len(rows),
        "unique_upperBizName": sorted(upper.keys()),
        "unique_middleBizName": sorted(middle.keys()),
        "unique_lowerBizName": sorted(lower.keys()),
        "upperBizName_counts": dict(upper.most_common()),
        "middleBizName_counts": dict(middle.most_common()),
        "lowerBizName_counts": dict(lower.most_common(50)),
        "hierarchy_triples": [
            {"upper": u, "middle": m, "lower": l, "count": c}
            for (u, m, l), c in triples.most_common(80)
        ],
    }


def suggest_service_mapping(summary: dict) -> dict[str, list[str]]:
    """수집된 middle/lower 명칭을 서비스 8유형에 휴리스틱 배치."""
    buckets: dict[str, list[str]] = defaultdict(list)
    rules = [
        ("카페", ["카페", "커피", "디저트", "베이커리", "제과"]),
        ("음식점", ["음식", "식당", "한식", "중식", "일식", "양식", "분식", "패스트푸드", "치킨", "피자"]),
        ("쇼핑시설", ["백화점", "마트", "쇼핑", "아울렛", "편의", "슈퍼", "상가", "문구", "화장품"]),
        ("관광지", ["관광", "명소", "유적", "사찰", "역", "터미널", "공항", "해변", "시장"]),
        ("문화시설", ["문화", "전시", "박물관", "미술", "공연", "극장", "영화", "CGV"]),
        ("공원", ["공원", "숲", "정원", "놀이", "테마파크"]),
        ("숙박시설", ["호텔", "모텔", "펜션", "숙박", "리조트"]),
    ]
    seen = set()
    for name in summary.get("unique_middleBizName", []) + summary.get("unique_lowerBizName", []):
        if not name or name in seen:
            continue
        seen.add(name)
        matched = False
        for service, kws in rules:
            if any(kw in name for kw in kws):
                buckets[service].append(name)
                matched = True
                break
        if not matched:
            buckets["기타(미분류)"].append(name)
    return dict(buckets)


def main() -> int:
    parser = argparse.ArgumentParser(description="TMAP POI category sampler")
    parser.add_argument(
        "--out",
        default=str(PROJECT_ROOT / "data" / "tmap_poi_category_samples.json"),
        help="Output JSON path",
    )
    parser.add_argument("--per-keyword", type=int, default=3, help="POIs per keyword")
    args = parser.parse_args()

    all_rows: list[dict] = []
    seen_ids: set[str] = set()

    for kw in SAMPLE_KEYWORDS:
        for poi in fetch_pois(kw, count=args.per_keyword):
            pid = str(poi.get("id") or poi.get("name") or "")
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            all_rows.append(extract_category_row(poi, kw))

    summary = build_summary(all_rows)
    suggested = suggest_service_mapping(summary)

    output = {
        "source": "TMAP POI Search API (/tmap/pois)",
        "keywords_queried": SAMPLE_KEYWORDS,
        "category_fields_observed": CATEGORY_FIELDS,
        "samples": all_rows,
        "summary": summary,
        "suggested_service_buckets": suggested,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Collected {len(all_rows)} unique POIs from {len(SAMPLE_KEYWORDS)} keywords")
    print(f"upperBizName unique: {len(summary['unique_upperBizName'])}")
    print(f"middleBizName unique: {len(summary['unique_middleBizName'])}")
    print(f"lowerBizName unique: {len(summary['unique_lowerBizName'])}")
    print(f"Written: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
