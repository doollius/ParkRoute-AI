from __future__ import annotations

from typing import Any

from utils.env_loader import get_env


def generate_explanation(route: dict[str, Any]) -> str:
    try:
        return _generate_openai(route)
    except Exception:
        return _generate_template(route)


def _generate_template(route: dict[str, Any]) -> str:
    summary = route.get("summary", {})
    parkings = route.get("parkings", [])

    lines = [
        "도보 이동을 줄이고 차량·주차 중심으로 방문 순서를 재구성했습니다.",
        f"총 이동 시간은 약 {summary.get('total_time_sec', 0) // 60}분 "
        f"(차량 {summary.get('car_time_sec', 0) // 60}분, "
        f"도보 {summary.get('walk_time_sec', 0) // 60}분)입니다.",
    ]
    if parkings:
        names = ", ".join(p["name"] for p in parkings[:3])
        lines.append(f"근처 공영주차장({names})을 기준으로 동선을 묶었습니다.")
    parking_cost = summary.get("parking_cost_won")
    if parking_cost:
        lines.append(f"예상 주차비는 약 {parking_cost:,}원입니다.")
    return " ".join(lines)


def _generate_openai(route: dict[str, Any]) -> str:
    key = get_env("OPENAI_API_KEY")
    if not key or key.lower().startswith("your"):
        return _generate_template(route)

    from openai import OpenAI

    summary = route.get("summary", {})
    stop_lines = []
    for s in route.get("stops", []):
        stop_lines.append(f"- {s.get('label', '?')}: {s.get('name', '')}")

    prompt = (
        "다음 여행 경로를 3~4문장으로 친절하게 설명해줘. "
        "도보 최소화와 주차장 선택 이유를 포함해.\n\n"
        f"방문 순서:\n" + "\n".join(stop_lines) + "\n\n"
        f"차량 {summary.get('car_time_sec', 0) // 60}분, "
        f"도보 {summary.get('walk_time_sec', 0) // 60}분, "
        f"주차 {summary.get('parking_count', 0)}회"
    )
    if summary.get("parking_cost_won"):
        prompt += f", 예상 주차비 {summary['parking_cost_won']:,}원"

    client = OpenAI(api_key=key)
    model = get_env("OPENAI_MODEL", "gpt-4o-mini")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a Korean travel route assistant for ParkRoute AI."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=300,
    )
    text = (resp.choices[0].message.content or "").strip()
    return text or _generate_template(route)
