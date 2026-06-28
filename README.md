# ParkRoute AI

주차 · 도보 · 차량을 고려한 **여행 동선 최적화** Streamlit 웹앱입니다.

네이버지도 등에서 모은 **도로명/지번 주소**를 입력하면, OR-Tools가 방문 순서를 재구성하고 TMAP으로 이동시간을 계산하며, 공영주차장과 GPT 설명을 제공합니다.

## 기능

- Place Card 입력 + TMAP Geocoding (POI fallback, 수동 좌표)
- 방문 규칙 (바로 다음 / 다음), 예약 시간, 출발 시각
- OR-Tools 최적화 + 공영주차장 추천 + 예상 주차비
- Folium 지도 (S → 1 → 2 → … → E 마커)
- OpenAI 경로 설명 (실패 시 템플릿 fallback)

## 로컬 실행

```powershell
cd TravelAgentProject
python -m pip install -r requirements.txt
copy .env.example .env
# .env 에 API 키 입력
python -m streamlit run app.py
```

### 필수 환경 변수 (`.env`)

| 변수 | 설명 |
|------|------|
| `TMAP_APP_KEY` | SK Open API TMAP |
| `DATA_GO_KR_SERVICE_KEY` | 공공데이터포털 주차장 |
| `OPENAI_API_KEY` | GPT 설명 (선택 가능, 없으면 템플릿) |
| `OPENAI_MODEL` | 기본 `gpt-4o-mini` |

API 연결 테스트:

```powershell
python scripts/test_api_keys.py
```

## Streamlit Cloud 배포

1. GitHub에 push (`.env` 제외)
2. [share.streamlit.io](https://share.streamlit.io) → New app → `app.py`
3. Settings → Secrets에 `.env`와 동일한 키 입력 (TOML 형식)
4. Redeploy

## 프로젝트 구조

```
app.py              # 진입점
pages/              # UI (start, input, review, loading, result)
controller/         # 화면 ↔ 서비스 조율
services/           # 비즈니스 로직, API 호출
optimizer/          # OR-Tools, 주차 그래프
api/                # TMAP, Geocoding, OpenAI
models/             # Place, Route 데이터
state/              # session_state
utils/              # 공통 유틸
```

## 설계 문서

상세 명세는 `Rules.md`를 참고하세요.

## 라이선스

Private / 포트폴리오용 — 별도 LICENSE 없음
