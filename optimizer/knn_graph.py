from __future__ import annotations

from constants.config import FORBIDDEN_EDGE_COST, KNN_EDGE_K
from optimizer.parking_graph import ClusterPlan
from utils.geo import haversine_m


def knn_neighbor_indices(
    node_index: int,
    coords: list[tuple[float, float]],
    k: int,
) -> list[int]:
    """직선 거리 기준 k-최근접 이웃 인덱스 (자기 자신 제외)."""
    n = len(coords)
    if n <= 1:
        return []
    lat0, lng0 = coords[node_index]
    ranked = sorted(
        (j for j in range(n) if j != node_index),
        key=lambda j: haversine_m(lat0, lng0, coords[j][0], coords[j][1]),
    )
    return ranked[: max(1, min(k, n - 1))]


def build_knn_edge_set(
    coords: list[tuple[float, float]],
    *,
    k: int = KNN_EDGE_K,
    cluster_plan: ClusterPlan | None = None,
) -> set[tuple[int, int]]:
    """Pass 1 TSP용 방향 엣지 — k-NN + 클러스터 내부 전쌍(연결 보장)."""
    n = len(coords)
    edges: set[tuple[int, int]] = set()
    if n <= 1:
        return edges

    for i in range(n):
        for j in knn_neighbor_indices(i, coords, k):
            edges.add((i, j))

    if cluster_plan:
        for indices in cluster_plan.clusters:
            if len(indices) < 2:
                continue
            for i in indices:
                for j in indices:
                    if i != j:
                        edges.add((i, j))

    # 연결성 보장: 컴포넌트 간 최단 직선 브릿지 1개
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, j in edges:
        union(i, j)

    for _ in range(n - 1):
        roots = {find(i) for i in range(n)}
        if len(roots) == 1:
            break
        bridged = False
        for i in range(n):
            for j in range(i + 1, n):
                if find(i) != find(j):
                    edges.add((i, j))
                    edges.add((j, i))
                    union(i, j)
                    bridged = True
                    break
            if bridged:
                break

    return edges


def apply_knn_forbidden_costs(
    cost_matrix: list[list[int]],
    allowed_edges: set[tuple[int, int]],
) -> list[list[int]]:
    """k-NN에 없는 호 제약 — OR-Tools가 해당 arc를 쓰지 못하게."""
    n = len(cost_matrix)
    sparse = [row[:] for row in cost_matrix]
    for i in range(n):
        for j in range(n):
            if i != j and (i, j) not in allowed_edges:
                sparse[i][j] = FORBIDDEN_EDGE_COST
    return sparse
