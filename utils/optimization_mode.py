from __future__ import annotations

MODE_MINIMIZE_WALK = "minimize_walk"
MODE_MINIMIZE_PARKING = "minimize_parking"

MODE_OPTIONS = [MODE_MINIMIZE_WALK, MODE_MINIMIZE_PARKING]

MODE_LABELS: dict[str, str] = {
    MODE_MINIMIZE_WALK: "도보 이동시간 최소화",
    MODE_MINIMIZE_PARKING: "주차 횟수 최소화",
}

MODE_DESCRIPTIONS: dict[str, str] = {
    MODE_MINIMIZE_WALK: "차량을 자주 이동하여 걷는 시간을 최소화합니다.",
    MODE_MINIMIZE_PARKING: (
        "공영주차장을 적극 활용하여 한 번 주차한 뒤 여러 장소를 도보로 방문합니다."
    ),
}


def normalize_optimization_mode(mode: str | None) -> str:
    """세션·레거시 값 정규화 (minimize_time → minimize_parking)."""
    if mode in (MODE_MINIMIZE_WALK, MODE_MINIMIZE_PARKING):
        return mode
    if mode == "minimize_time":
        return MODE_MINIMIZE_PARKING
    return MODE_MINIMIZE_WALK


def mode_label(mode: str | None) -> str:
    return MODE_LABELS.get(normalize_optimization_mode(mode), MODE_LABELS[MODE_MINIMIZE_WALK])
