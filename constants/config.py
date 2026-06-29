WALK_TIME_LIMIT_MINUTES = 9
WALK_TIME_FALLBACK_MINUTES = 12
MAX_GRAPH_NODES = 30
OPTIMIZATION_TIMEOUT_SEC = 10

# Parking optimization (Rules.md SC-004, §6.2)
PARKING_TRANSITION_PENALTY = 25 * 60 * 10  # inter-cluster edge penalty (car-cost scale)
PARKING_COUNT_MODE_PENALTY = 100 * 60 * 100  # 주차 횟수 최소화 — 차량 이동(주차) 횟수 우선
PARKING_SCORE_DIST_WEIGHT = 0.6
PARKING_SCORE_FEE_WEIGHT = 0.4
PARKING_CANDIDATES_PER_CLUSTER = 8
PARKING_NEARBY_RADIUS_M = 1000  # POI ↔ 주차장 직선 거리 상한 (클러스터 매칭)
PARKING_WALK_MAX_DISTANCE_M = 1000  # 주차 횟수 모드: TMAP 도보 경로 거리 상한

# Kakao Local API — 주차장(PK6) 반경 검색
KAKAO_PARKING_CATEGORY_CODE = "PK6"
KAKAO_PARKING_SEARCH_RADIUS_M = 2000  # 여행 중심 좌표 기준 검색 반경
KAKAO_PARKING_MAX_DISTANCE_M = 2000  # 카카오 distance 필드 1차 필터 (검색 반경과 동일)
KAKAO_PARKING_PAGE_SIZE = 15  # 카카오 API 페이지당 최대 15건
KAKAO_PARKING_MAX_RESULTS = 45  # 카카오 category 검색 최대 45건
KAKAO_PUBLIC_NAME_BONUS = 0.15  # score_parking: 이름에 «공영» 포함 시 가산
PARKING_SEARCH_PENALTY_SEC = 7 * 60  # 목적지 주차 시 탐색·진입 부담 (도보 최소화 비교용)
FORBIDDEN_EDGE_COST = 999_999_999  # 클러스터 내 POI 직행 차량 금지

OPENAI_MODEL_DEFAULT = "gpt-4o-mini"

APP_TITLE = "ParkRoute AI"
APP_TAGLINE = "주차 · 도보 · 차량을 고려한 여행 동선 최적화"
