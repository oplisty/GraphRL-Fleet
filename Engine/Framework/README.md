# Framework (B 组仿真内核)

这个目录实现了 B 组任务：仿真引擎、图结构地图、寻路、电量与充电排队约束、统一调度接口、日志输出。

当前任务语义采用单点服务模型：任务在 `origin_node` 完成服务后视为完成；为保证约束一致性，车辆完成任务后会自动回仓（或在电量不足时先去充电）。

依赖安装（建议）：

```bash
pip install -r Engine/requirements.txt
```

## 目录结构

```text
Framework/
├── core/
│   ├── config.py        # 场景/仿真配置
│   ├── entities.py      # Vehicle / Task / ChargingStation / Depot
│   ├── graph.py         # 邻接表图结构
│   ├── pathfinder.py    # Dijkstra + 距离缓存 + 电量可达性检查
│   ├── simulation.py    # Environment 核心引擎（step/run/dispatch）
│   └── logger.py        # JSON/CSV 日志输出
├── generator/
│   ├── map_generator.py # 随机地图与站点生成
│   └── task_generator.py# 动态任务生成
├── scheduler/
│   ├── base.py          # Scheduler 抽象接口
│   ├── nearest_task.py  # 最近任务优先基线
│   └── heaviest_task.py # 最大重量优先基线
├── configs/
│   ├── random_baseline.yaml
│   ├── panyu_json_baseline.yaml
│   ├── panyu_processed_baseline.yaml
│   └── experiment_matrix.yaml
└── examples/
    └── run_baseline.py  # 快速运行脚本
```

## 对 A 组提供的核心 API

`Environment` (位于 `core/simulation.py`)：

- `get_available_tasks(t=None)`
- `get_vehicle_state(vehicle_id)`
- `dispatch(vehicle_id, task_id)`
- `get_state_snapshot(raw=False)` / `get_serializable_snapshot()`
- `export_state_snapshot_json(path)`
- `step(actions=None)`
- `run(end_time=None, scheduler=None)`
- `export_logs(output_dir)`

## 对 C 组提供的日志

输出 `json/csv`：

- `step_log`：每个时间步总览（得分、完成/超时任务、平均电量、总排队长度）
- `vehicle_log`：车辆状态时间序列（位置、电量、状态、里程）
- `task_log`：任务状态变化（released/assigned/completed/expired）
- `station_log`：充电站队列与占用状态
- `events`：关键事件（无法充电、开始/结束充电等）

## 建模说明

- 任务完成判定：车辆到达任务点即完成服务（单点服务假设）。
- 协同任务扩展：支持 `dispatch(task_id, {vehicle_id: load, ...})` 的拆分运输模型；多车不要求同步到达，按累计配送重量完成任务。
- 默认基线：`collaborative_task_ratio=0.0`，即默认单车单任务；协同任务需显式开启。
- 回仓一致性：派单前检查“可完成任务并可回仓”，执行中也会自动回仓。
- 充电站选择：不只看距离，还考虑 `queue_length` 和 `occupied_piles` 负荷。
- 收益统计：按任务实际执行距离与等待时间计算，不再使用纯理论最短路距离。
- 评分函数定位：课程项目自定义评价指标，用于策略横向对比，不代表真实商业收益模型。

## 运行示例

在仓库根目录执行：

```bash
python -m Framework.examples.run_baseline --config "Framework/configs/random_baseline.yaml"
python -m Framework.examples.run_panyu_baseline --config "Framework/configs/panyu_json_baseline.yaml"
python -m Framework.examples.run_panyu_processed_baseline --config "Framework/configs/panyu_processed_baseline.yaml"
python -m Framework.examples.run_experiment_matrix --config "Framework/configs/experiment_matrix.yaml"
python -m Framework.examples.run_baseline --config "Framework/configs/random_baseline.yaml" --collaborative-task-ratio 0.3
python -m Framework.examples.run_a_group_integration_smoke
```

可用 CLI 临时覆盖 YAML：

```bash
python -m Framework.examples.run_panyu_processed_baseline \
  --config "Framework/configs/panyu_processed_baseline.yaml" \
  --scheduler heaviest --tasks 200
```

日志默认写入：`Framework/output/baseline/<scale>_<scheduler>/`

## 文档

- `../docs/00-文档总览.md`
- `../docs/01-快速开始与常用命令.md`
- `../docs/02-协作接口说明.md`
- `../docs/03-场景分析与数据结构.md`
