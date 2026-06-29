"""
TMAP POI 검색 API(/tmap/pois)로 middleBizName / lowerBizName 조합을 최대한 수집해 CSV로 저장.

TMAP에는 '전체 카테고리 목록' 전용 API가 없어, 다양한 검색어·페이지·반복 확장으로 수집합니다.

Usage:
    python scripts/extract_tmap_category_list.py
    python scripts/extract_tmap_category_list.py --out data/category_list.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# TMAP 주변 카테고리 검색 문서의 업종명 + 여행·생활 검색어
SEED_KEYWORDS = [
  # 생활
  "T와이파이존", "목욕탕", "숙박", "쇼핑", "관공서", "주요시설물", "은행", "ATM", "편의점",
  "미용실", "이발소", "대형마트", "화장실", "공원", "커피", "음식", "레저", "호텔", "마트",
  # 식음료
  "식음료", "TV맛집", "카페", "한식", "중식", "일식", "패밀리레스토랑", "전문음식점",
  "피자", "치킨", "디저트", "제과점", "베스킨라빈스", "하겐다즈", "나뚜루", "콜드스톤", "패스트푸드",
  # 교통
  "교통", "버스", "버스정류장", "지하철", "주유소", "충전소", "주차장", "정비소",
  "EV충전소", "EV가스충전소",
  # 병원
  "병원", "약국", "내과", "소아과", "외과", "치과", "안과", "의원", "보건소", "한의원",
  # 놀거리
  "놀거리", "영화관", "노래방", "PC방", "공연장", "문화시설", "스크린골프장",
  # 추가 광범위 검색어
  "관광", "명소", "박물관", "미술관", "역", "터미널", "공항", "학교", "대학교", "유치원",
  "교회", "사찰", "성당", "시장", "해변", "해수욕장", "산", "등산", "캠핑", "리조트",
  "모텔", "펜션", "게스트하우스", "백화점", "아울렛", "슈퍼마켓", "이마트", "홈플러스",
  "롯데마트", "GS25", "CU", "세븐일레븐", "올리브영", "다이소", "서점", "문구점",
  "주차", "정류장", "철도", "기차역", "고속버스", "항구", "부두", "항만",
  "음식점", "맛집", "분식", "양식", "뷔페", "술집", "바", "포차",
  "극장", "전시", "갤러리", "도서관", "체육관", "수영장", "골프", "스키",
  "놀이공원", "테마파크", "동물원", "수족관", "식물원", "유적", "유원지",
  "주유", "세차", "카센터", "타이어", "렌터카",
  "산부인과", "정형외과", "피부과", "이비인후과", "신경외과", "응급실",
  "동물병원", "약국", "한방", "요양원",
  "부동산", "세무서", "구청", "시청", "경찰서", "소방서", "우체국", "법원",
  "공영주차장", "주차타워", "휴게소", "톨게이트",
  "찜질방", "사우나", "스파", "마사지",
  "학원", "독서실", "어린이집",
  "농장", "와이너리", "막걸리", "찻집", "베이커리",
  "관광지", "전망대", "등대", "폭포", "계곡", "섬", "항구",
  "백화점", "상가", "전통시장", "재래시장", "농수산물",
  "CGV", "롯데시네마", "메가박스",
  "스타벅스", "맥도날드", "버거킹", "KFC", "던킨",
  "경복궁", "불국사", "해운대", "제주", "강릉", "전주", "수원", "인천",
]

# 초성·단음절로 누락 카테고리 보완
HANGUL_SEEDS = list("가나다라마바사아자차카타파하") + [
  "거", "고", "구", "기", "나", "노", "누", "니", "다", "도", "두", "디",
  "라", "로", "루", "리", "마", "모", "무", "미", "바", "보", "부", "비",
  "사", "소", "수", "시", "아", "오", "우", "이", "자", "조", "주", "지",
  "차", "초", "추", "치", "카", "코", "쿠", "키", "타", "토", "투", "티",
  "파", "포", "푸", "피", "하", "호", "후", "히",
]


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    return str(value).replace("\\/", "/").strip()


def _app_key() -> str:
    key = os.getenv("TMAP_APP_KEY", "").strip()
    if not key:
        raise SystemExit("TMAP_APP_KEY가 .env에 없습니다.")
    return key


def fetch_poi_page(
    session: requests.Session,
    keyword: str,
    page: int,
    count: int,
) -> list[dict]:
    resp = session.get(
        "https://apis.openapi.sk.com/tmap/pois",
        params={
            "version": "1",
            "searchKeyword": keyword.strip(),
            "searchType": "all",
            "page": page,
            "count": count,
            "reqCoordType": "WGS84GEO",
            "resCoordType": "WGS84GEO",
            "multiPoint": "N",
            "poiGroupYn": "N",
        },
        timeout=20,
    )
    if resp.status_code != 200:
        return []

    pois = resp.json().get("searchPoiInfo", {}).get("pois", {}).get("poi", [])
    if isinstance(pois, dict):
        pois = [pois]
    return pois or []


def collect_categories(
    keywords: list[str],
    *,
    pages_per_keyword: int,
    count_per_page: int,
    sleep_sec: float,
) -> set[tuple[str, str]]:
    session = requests.Session()
    session.headers.update({"appKey": _app_key(), "Accept": "application/json"})

    pairs: set[tuple[str, str]] = set()
    seen_poi: set[str] = set()

    for ki, keyword in enumerate(keywords, 1):
        if not keyword.strip():
            continue
        for page in range(1, pages_per_keyword + 1):
            pois = fetch_poi_page(session, keyword, page, count_per_page)
            if not pois:
                break

            for poi in pois:
                pid = str(poi.get("pkey") or poi.get("id") or "")
                if pid:
                    seen_poi.add(pid)

                middle = _normalize(poi.get("middleBizName"))
                lower = _normalize(poi.get("lowerBizName"))
                if middle and lower:
                    pairs.add((middle, lower))

                # 그룹 하부 POI 업종 (지하철 출구 등)
                group = poi.get("groupSubLists", {})
                subs = group.get("groupSub", []) if isinstance(group, dict) else []
                if isinstance(subs, dict):
                    subs = [subs]
                for sub in subs:
                    sub_middle = _normalize(sub.get("subClassNmB"))
                    sub_lower = _normalize(sub.get("subClassNmC"))
                    if sub_middle and sub_lower:
                        pairs.add((sub_middle, sub_lower))

            time.sleep(sleep_sec)

        if ki % 20 == 0:
            print(
                f"  keywords {ki}/{len(keywords)} → pairs {len(pairs)} (POIs {len(seen_poi)})",
                flush=True,
            )

    return pairs


def expand_keywords(
    pairs: set[tuple[str, str]],
    existing: set[str],
    *,
    max_new: int = 80,
) -> list[str]:
    """발견된 middle/lower 명칭으로 검색어 확장 (과도한 API 호출 방지)."""
    new: list[str] = []
    middles = sorted({m for m, _ in pairs if m})
    lowers = sorted({l for _, l in pairs if l})
    # middle 우선(상위 개념), 이후 lower
    for term in middles + lowers:
        if term and term not in existing:
            existing.add(term)
            new.append(term)
            if len(new) >= max_new:
                break
    return new


def write_csv(path: Path, pairs: set[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(pairs, key=lambda x: (x[0], x[1]))
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["middleBizName", "lowerBizName"])
        for middle, lower in rows:
            writer.writerow([middle, lower])


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract TMAP POI category pairs to CSV")
    parser.add_argument(
        "--out",
        default=str(PROJECT_ROOT / "data" / "category_list.csv"),
        help="Output CSV path",
    )
    parser.add_argument("--pages", type=int, default=12, help="Pages per keyword (max useful ~50)")
    parser.add_argument("--count", type=int, default=20, help="POIs per page (1-20)")
    parser.add_argument("--rounds", type=int, default=2, help="Expansion rounds using discovered terms")
    parser.add_argument("--max-expand", type=int, default=80, help="Max new keywords per expansion round")
    parser.add_argument("--sleep", type=float, default=0.05, help="Delay between API calls (sec)")
    args = parser.parse_args()

    keyword_set = set(SEED_KEYWORDS + HANGUL_SEEDS)
    keywords = list(dict.fromkeys(SEED_KEYWORDS + HANGUL_SEEDS))
    all_pairs: set[tuple[str, str]] = set()

    print(f"Round 0: {len(keywords)} seed keywords", flush=True)
    all_pairs |= collect_categories(
        keywords,
        pages_per_keyword=args.pages,
        count_per_page=min(20, max(1, args.count)),
        sleep_sec=args.sleep,
    )
    print(f"After round 0: {len(all_pairs)} unique (middle, lower) pairs", flush=True)

    for rnd in range(1, args.rounds + 1):
        extra = expand_keywords(all_pairs, keyword_set, max_new=args.max_expand)
        if not extra:
            print(f"Round {rnd}: no new keywords, stop.", flush=True)
            break
        print(f"Round {rnd}: +{len(extra)} keywords from discovered categories", flush=True)
        all_pairs |= collect_categories(
            extra,
            pages_per_keyword=max(4, args.pages // 2),
            count_per_page=min(20, max(1, args.count)),
            sleep_sec=args.sleep,
        )
        print(f"After round {rnd}: {len(all_pairs)} unique pairs", flush=True)

    out_path = Path(args.out)
    write_csv(out_path, all_pairs)

    print(f"Written {len(all_pairs)} rows → {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
