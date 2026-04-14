from __future__ import annotations

"""
小规模“上帝视角”离线 MILP 基线：
- 所有任务在优化开始时已知（release/deadline/demand/location）
- 多车辆联合优化全局路径与调度
- 车辆 SOC（电量）约束
- 载重与载重相关能耗
- 速度离散选择（影响时间与能耗）
- 充电站可多次访问（通过站点复制节点）
- 支持线性充电 / 分段线性近似的“非线性”充电
- 通过 Gurobi 或 CPLEX 求解（经 PuLP 后端调用）

说明：
1) 这是课程大作业用的“小规模精确求解 baseline”，优先可解释性和可运行性。
2) 规模增大后，MILP 复杂度会迅速上升。
"""

from dataclasses import asdict, dataclass
from math import hypot
from pathlib import Path
from typing import Literal

import csv
import json
import pulp as pl

SolverName = Literal["gurobi", "cplex"]
ChargeMode = Literal["linear", "piecewise"]


@dataclass(slots=True)
class Task:
    id: int
    x: float
    y: float
    demand: float
    release: float
    deadline: float
    service_time: float = 2.0


@dataclass(slots=True)
class Station:
    id: int
    x: float
    y: float


@dataclass(slots=True)
class OfflineInstance:
    num_vehicles: int
    vehicle_capacity: float
    battery_capacity: float
    horizon: float
    depot_x: float
    depot_y: float
    tasks: list[Task]
    stations: list[Station]
    max_station_visits_per_station: int = 2
    graph_data: dict | None = None

    # 速度离散层（km / min）
    speed_levels: tuple[float, ...] = (0.8, 1.0, 1.2)

    # 能耗模型（kWh / km）：base + speed_coeff*speed_idx + load_coeff*(load/cap)
    energy_base_per_km: float = 0.9
    energy_speed_coeff: float = 0.08
    energy_load_coeff: float = 0.4

    # 充电（线性）
    linear_charge_rate: float = 3.0  # kWh / min

    # 充电（分段近似“非线性”）: 每段 (最大充电量, 该段充电速率)
    # 前段快、后段慢，模拟 CC-CV 趋势
    piecewise_segments: tuple[tuple[float, float], ...] = (
        (30.0, 5.0),
        (30.0, 3.0),
        (40.0, 1.8),
    )


@dataclass(slots=True)
class SolveResult:
    status: str
    objective: float
    total_distance: float
    total_tardiness: float
    makespan: float
    routes: dict[int, list[str]]


class GodViewMILP:
    def __init__(self, inst: OfflineInstance, solver: SolverName = "gurobi", charge_mode: ChargeMode = "piecewise"):
        self.inst = inst
        self.solver_name = solver
        self.charge_mode = charge_mode

        self.nodes: list[str] = []
        self.node_coord: dict[str, tuple[float, float]] = {}
        self.node_type: dict[str, str] = {}
        self.task_of_node: dict[str, Task] = {}
        self.station_of_node: dict[str, Station] = {}

        self._build_expanded_nodes()
        self.dist = self._build_dist_matrix()

    def _build_expanded_nodes(self) -> None:
        self.nodes = ["DEPOT_START", "DEPOT_END"]
        self.node_type["DEPOT_START"] = "depot_start"
        self.node_type["DEPOT_END"] = "depot_end"
        self.node_coord["DEPOT_START"] = (self.inst.depot_x, self.inst.depot_y)
        self.node_coord["DEPOT_END"] = (self.inst.depot_x, self.inst.depot_y)

        for t in self.inst.tasks:
            n = f"T_{t.id}"
            self.nodes.append(n)
            self.node_type[n] = "task"
            self.node_coord[n] = (t.x, t.y)
            self.task_of_node[n] = t

        for s in self.inst.stations:
            for k in range(self.inst.max_station_visits_per_station):
                n = f"S_{s.id}_{k}"
                self.nodes.append(n)
                self.node_type[n] = "station"
                self.node_coord[n] = (s.x, s.y)
                self.station_of_node[n] = s

    def _build_dist_matrix(self) -> dict[tuple[str, str], float]:
        dist: dict[tuple[str, str], float] = {}
        for i in self.nodes:
            xi, yi = self.node_coord[i]
            for j in self.nodes:
                if i == j:
                    continue
                if i == "DEPOT_END":
                    continue
                if j == "DEPOT_START":
                    continue
                xj, yj = self.node_coord[j]
                dist[(i, j)] = hypot(xi - xj, yi - yj)
        return dist

    def _select_solver(self) -> pl.LpSolver:
        if self.solver_name == "gurobi":
            if hasattr(pl, "GUROBI"):
                return pl.GUROBI(msg=True)
            if hasattr(pl, "GUROBI_CMD"):
                return pl.GUROBI_CMD(msg=True)
            raise RuntimeError("未检测到 Gurobi 后端，请先安装 gurobipy 并配置许可证。")

        if self.solver_name == "cplex":
            if hasattr(pl, "CPLEX_PY"):
                return pl.CPLEX_PY(msg=True)
            if hasattr(pl, "CPLEX_CMD"):
                return pl.CPLEX_CMD(msg=True)
            raise RuntimeError("未检测到 CPLEX 后端，请先安装 cplex/docplex 并配置许可。")

        raise ValueError(f"未知 solver: {self.solver_name}")

    def solve(self, time_limit_sec: int = 120) -> SolveResult:
        inst = self.inst
        V = list(range(inst.num_vehicles))
        N = list(self.nodes)
        S = list(range(len(inst.speed_levels)))

        arcs = list(self.dist.keys())
        task_nodes = [n for n in N if self.node_type[n] == "task"]
        station_nodes = [n for n in N if self.node_type[n] == "station"]

        model = pl.LpProblem("god_view_small_milp", pl.LpMinimize)

        x = pl.LpVariable.dicts("x", ((v, i, j) for v in V for (i, j) in arcs), 0, 1, cat="Binary")
        y = pl.LpVariable.dicts("y", ((v, i, j, s) for v in V for (i, j) in arcs for s in S), 0, 1, cat="Binary")

        visit = pl.LpVariable.dicts("visit", ((v, n) for v in V for n in N if n not in {"DEPOT_START", "DEPOT_END"}), 0, 1, cat="Binary")
        use = pl.LpVariable.dicts("use", V, 0, 1, cat="Binary")

        arr = pl.LpVariable.dicts("arr", ((v, n) for v in V for n in N), lowBound=0)
        load = pl.LpVariable.dicts("load", ((v, n) for v in V for n in N), lowBound=0, upBound=inst.vehicle_capacity)
        soc = pl.LpVariable.dicts("soc", ((v, n) for v in V for n in N), lowBound=0, upBound=inst.battery_capacity)

        charge = pl.LpVariable.dicts("chg", ((v, n) for v in V for n in N), lowBound=0, upBound=inst.battery_capacity)
        charge_time = pl.LpVariable.dicts("chg_t", ((v, n) for v in V for n in N), lowBound=0)

        tardy = pl.LpVariable.dicts("tardy", ((v, n) for v in V for n in task_nodes), lowBound=0)
        e_arc = pl.LpVariable.dicts("e", ((v, i, j) for v in V for (i, j) in arcs), lowBound=0)
        w_load = pl.LpVariable.dicts("w", ((v, i, j) for v in V for (i, j) in arcs), lowBound=0, upBound=inst.vehicle_capacity)

        max_end = pl.LpVariable("max_end", lowBound=0)

        # x-y 绑定：每条弧选择一个速度层
        for v in V:
            for i, j in arcs:
                model += pl.lpSum(y[(v, i, j, s)] for s in S) == x[(v, i, j)]

        # 每车从 start 出发，回到 end
        for v in V:
            model += pl.lpSum(x[(v, "DEPOT_START", j)] for j in N if ("DEPOT_START", j) in self.dist) == use[v]
            model += pl.lpSum(x[(v, i, "DEPOT_END")] for i in N if (i, "DEPOT_END") in self.dist) == use[v]

        # 流守恒 + visit
        for v in V:
            for n in N:
                if n in {"DEPOT_START", "DEPOT_END"}:
                    continue
                incoming = pl.lpSum(x[(v, i, n)] for i in N if (i, n) in self.dist)
                outgoing = pl.lpSum(x[(v, n, j)] for j in N if (n, j) in self.dist)
                model += incoming == visit[(v, n)]
                model += outgoing == visit[(v, n)]

        # 每个任务恰好一次
        for n in task_nodes:
            model += pl.lpSum(visit[(v, n)] for v in V) == 1

        # 每个“站点副本”最多一次（可实现同站多次访问：通过多个副本）
        for n in station_nodes:
            model += pl.lpSum(visit[(v, n)] for v in V) <= 1

        # 载重初始化（从仓库带出的总需求）
        for v in V:
            model += load[(v, "DEPOT_START")] == pl.lpSum(self.task_of_node[n].demand * visit[(v, n)] for n in task_nodes)

        M_load = inst.vehicle_capacity
        for v in V:
            for i, j in arcs:
                demand_j = self.task_of_node[j].demand if j in task_nodes else 0.0
                model += load[(v, j)] <= load[(v, i)] - demand_j + M_load * (1 - x[(v, i, j)])
                model += load[(v, j)] >= load[(v, i)] - demand_j - M_load * (1 - x[(v, i, j)])

        # SOC 初始化
        for v in V:
            model += soc[(v, "DEPOT_START")] == inst.battery_capacity

        # 仅站点可充电
        for v in V:
            for n in N:
                if self.node_type[n] != "station":
                    model += charge[(v, n)] == 0
                    model += charge_time[(v, n)] == 0

        # 线性 / 分段充电时间模型
        if self.charge_mode == "linear":
            for v in V:
                for n in station_nodes:
                    model += charge_time[(v, n)] >= charge[(v, n)] / inst.linear_charge_rate
        else:
            segs = list(inst.piecewise_segments)
            z = pl.LpVariable.dicts(
                "zseg",
                ((v, n, k) for v in V for n in station_nodes for k in range(len(segs))),
                lowBound=0,
            )
            b = pl.LpVariable.dicts(
                "bseg",
                ((v, n, k) for v in V for n in station_nodes for k in range(len(segs))),
                lowBound=0,
                upBound=1,
                cat="Binary",
            )
            for v in V:
                for n in station_nodes:
                    model += charge[(v, n)] == pl.lpSum(z[(v, n, k)] for k in range(len(segs)))
                    model += charge_time[(v, n)] >= pl.lpSum(z[(v, n, k)] / segs[k][1] for k in range(len(segs)))
                    for k, (cap_k, _) in enumerate(segs):
                        model += z[(v, n, k)] <= cap_k * b[(v, n, k)]
                    for k in range(1, len(segs)):
                        model += b[(v, n, k)] <= b[(v, n, k - 1)]

        # 能耗线性化 + SOC 迁移
        M_soc = inst.battery_capacity
        for v in V:
            for i, j in arcs:
                d = self.dist[(i, j)]

                # w_load = load_i * x_ij (线性化)
                model += w_load[(v, i, j)] <= load[(v, i)]
                model += w_load[(v, i, j)] <= inst.vehicle_capacity * x[(v, i, j)]
                model += w_load[(v, i, j)] >= load[(v, i)] - inst.vehicle_capacity * (1 - x[(v, i, j)])

                # 速度因子（用速度层索引做能耗增量）
                speed_idx_expr = pl.lpSum((s + 1) * y[(v, i, j, s)] for s in S)

                model += (
                    e_arc[(v, i, j)]
                    == d * inst.energy_base_per_km * x[(v, i, j)]
                    + d * inst.energy_speed_coeff * speed_idx_expr
                    + d * inst.energy_load_coeff / inst.vehicle_capacity * w_load[(v, i, j)]
                )

                # SOC 迁移（j 点离开时 SOC）
                model += soc[(v, j)] <= soc[(v, i)] - e_arc[(v, i, j)] + charge[(v, j)] + M_soc * (1 - x[(v, i, j)])
                model += soc[(v, j)] >= soc[(v, i)] - e_arc[(v, i, j)] + charge[(v, j)] - M_soc * (1 - x[(v, i, j)])

        # 时间递推（travel + service + charge）
        M_t = inst.horizon * 4
        for v in V:
            model += arr[(v, "DEPOT_START")] == 0
            for i, j in arcs:
                d = self.dist[(i, j)]
                travel = pl.lpSum(d / inst.speed_levels[s] * y[(v, i, j, s)] for s in S)

                service_i = self.task_of_node[i].service_time if i in task_nodes else 0.0
                model += arr[(v, j)] >= arr[(v, i)] + service_i + charge_time[(v, i)] + travel - M_t * (1 - x[(v, i, j)])

        # 任务时间窗 + 迟到
        for v in V:
            for n in task_nodes:
                t = self.task_of_node[n]
                model += arr[(v, n)] >= t.release - M_t * (1 - visit[(v, n)])
                model += arr[(v, n)] <= t.deadline + tardy[(v, n)] + M_t * (1 - visit[(v, n)])
                model += tardy[(v, n)] <= M_t * visit[(v, n)]

        # 工期定义
        for v in V:
            model += max_end >= arr[(v, "DEPOT_END")]

        # 目标：总里程 + 迟到惩罚 + 工期
        total_distance_expr = pl.lpSum(self.dist[(i, j)] * x[(v, i, j)] for v in V for (i, j) in arcs)
        total_tardy_expr = pl.lpSum(tardy[(v, n)] for v in V for n in task_nodes)

        model += total_distance_expr + 25.0 * total_tardy_expr + 0.2 * max_end

        solver = self._select_solver()
        if hasattr(solver, "timeLimit"):
            solver.timeLimit = time_limit_sec

        status_code = model.solve(solver)
        status = pl.LpStatus.get(status_code, "Unknown")

        routes = self._extract_routes(x, V)
        result = SolveResult(
            status=status,
            objective=float(pl.value(model.objective) or 0.0),
            total_distance=float(pl.value(total_distance_expr) or 0.0),
            total_tardiness=float(pl.value(total_tardy_expr) or 0.0),
            makespan=float(pl.value(max_end) or 0.0),
            routes=routes,
        )
        return result

    def save_result(self, result: SolveResult, out_dir: str | Path, prefix: str = "god_view_milp") -> tuple[Path, Path, Path]:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)

        summary_json = out / f"{prefix}_summary.json"
        summary_csv = out / f"{prefix}_summary.csv"
        route_csv = out / f"{prefix}_routes.csv"

        payload = {
            "solver": self.solver_name,
            "charge_mode": self.charge_mode,
            "instance": {
                **asdict(self.inst),
                "tasks": [asdict(t) for t in self.inst.tasks],
                "stations": [asdict(s) for s in self.inst.stations],
            },
            "result": {
                "status": result.status,
                "objective": result.objective,
                "total_distance": result.total_distance,
                "total_tardiness": result.total_tardiness,
                "makespan": result.makespan,
                "routes": result.routes,
            },
        }
        summary_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        with summary_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "solver",
                    "charge_mode",
                    "status",
                    "objective",
                    "total_distance",
                    "total_tardiness",
                    "makespan",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "solver": self.solver_name,
                    "charge_mode": self.charge_mode,
                    "status": result.status,
                    "objective": round(result.objective, 6),
                    "total_distance": round(result.total_distance, 6),
                    "total_tardiness": round(result.total_tardiness, 6),
                    "makespan": round(result.makespan, 6),
                }
            )

        with route_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["vehicle_id", "seq", "node", "node_type", "task_id", "station_id"],
            )
            writer.writeheader()
            for vid, route in sorted(result.routes.items()):
                for seq, node in enumerate(route):
                    node_type = self.node_type.get(node, "unknown")
                    task_id = ""
                    station_id = ""
                    if node.startswith("T_"):
                        task_id = node[2:]
                    elif node.startswith("S_"):
                        station_id = node.split("_")[1]
                    writer.writerow(
                        {
                            "vehicle_id": vid,
                            "seq": seq,
                            "node": node,
                            "node_type": node_type,
                            "task_id": task_id,
                            "station_id": station_id,
                        }
                    )

        return summary_json, summary_csv, route_csv

    def _extract_routes(self, x: dict, vehicles: list[int]) -> dict[int, list[str]]:
        routes: dict[int, list[str]] = {}
        for v in vehicles:
            nxt: dict[str, str] = {}
            for (i, j), _d in self.dist.items():
                val = pl.value(x[(v, i, j)])
                if val is not None and val > 0.5:
                    nxt[i] = j

            path = ["DEPOT_START"]
            cur = "DEPOT_START"
            seen = {cur}
            while cur in nxt:
                cur = nxt[cur]
                path.append(cur)
                if cur in seen or cur == "DEPOT_END":
                    break
                seen.add(cur)
            routes[v] = path
        return routes


def build_tiny_demo_instance() -> OfflineInstance:
    tasks = [
        Task(id=1, x=8, y=3, demand=18, release=0, deadline=60),
        Task(id=2, x=14, y=7, demand=22, release=5, deadline=85),
        Task(id=3, x=6, y=12, demand=15, release=0, deadline=70),
        Task(id=4, x=18, y=14, demand=20, release=10, deadline=95),
    ]
    stations = [
        Station(id=1, x=10, y=8),
        Station(id=2, x=16, y=4),
    ]
    return OfflineInstance(
        num_vehicles=2,
        vehicle_capacity=55,
        battery_capacity=100,
        horizon=180,
        depot_x=0,
        depot_y=0,
        tasks=tasks,
        stations=stations,
        max_station_visits_per_station=2,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="离线上帝视角 MILP 小规模全局最优基线")
    parser.add_argument("--solver", choices=["gurobi", "cplex"], default="gurobi")
    parser.add_argument("--charge-mode", choices=["linear", "piecewise"], default="piecewise")
    parser.add_argument("--time-limit", type=int, default=120)
    parser.add_argument("--out-dir", default="policy/offline/output")
    parser.add_argument("--prefix", default="god_view_milp")
    args = parser.parse_args()

    inst = build_tiny_demo_instance()
    engine = GodViewMILP(inst, solver=args.solver, charge_mode=args.charge_mode)
    res = engine.solve(time_limit_sec=args.time_limit)
    json_path, summary_csv, route_csv = engine.save_result(res, out_dir=args.out_dir, prefix=args.prefix)

    print("=== God-View MILP Result ===")
    print(f"status          : {res.status}")
    print(f"objective       : {res.objective:.4f}")
    print(f"total_distance  : {res.total_distance:.4f}")
    print(f"total_tardiness : {res.total_tardiness:.4f}")
    print(f"makespan        : {res.makespan:.4f}")
    for v, route in res.routes.items():
        print(f"vehicle-{v}: {' -> '.join(route)}")

    print("=== Saved Files ===")
    print(f"json : {json_path}")
    print(f"csv1 : {summary_csv}")
    print(f"csv2 : {route_csv}")


if __name__ == "__main__":
    main()
