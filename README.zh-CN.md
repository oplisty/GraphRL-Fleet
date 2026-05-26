# 新能源物流车队协同调度系统

[English README](README.md)

本项目面向“新能源物流车队协同调度”课程大作业，目标是在动态图结构道路网络上模拟新能源物流车辆的任务分配、路径规划、充电补能和调度策略对比。系统采用“仿真引擎 + 策略算法 + 后端服务 + 前端可视化”的结构，既可以运行基础启发式策略，也可以训练 Q-learning 超启发式策略，并提供小规模 MILP 上界作为对比参考。项目还包含广州番禺区实地道路网络数据，可在真实城市路网节点和充电站数据上进行仿真测试。

## 项目结构

```text
Data-Structure-HW/
├── Engine/                          # 仿真引擎、后端、地图数据和实验入口
│   ├── Framework/
│   │   ├── api/                     # FastAPI + WebSocket 后端
│   │   ├── configs/                 # YAML 实验配置
│   │   ├── core/                    # 图、实体、寻路、日志、仿真核心
│   │   ├── examples/                # 可运行实验入口
│   │   ├── generator/               # 随机/真实地图与任务生成
│   │   └── scheduler/               # 启发式调度器与离线回放调度器
│   └── Map Resource/                # 广州番禺真实地图数据与预处理脚本
├── UI/logistics-ui/                 # Next.js 可视化前端
├── policy/
│   ├── gymnasium_qlearning/         # Gymnasium + Q-learning 策略
│   └── offline/                     # MILP 上帝视角基线
├── experiments/                     # 绘图脚本和运行后生成的实验输出
├── 2026-大作业要求.txt               # 原始大作业要求
├── requirements.txt                 # Python 依赖
└── run_all_experiments.sh           # 批量实验脚本
```

## 大作业要求

新能源物流车队协同调度：假设你是一个中央仓库的管理者，配置了一支新能源车队。面对城市中随时可能出现的调度任务，如何规划新能源车辆的路径。要求使用图结构实现道路和寻路。

1. 车队中车辆数目有限，且每辆车具有电量上限和载重上限，系统需模拟一段时间内动态出现的任务。
2. 每一处产生的任务包含产生时间、地点坐标、和货物重量（随机数生成）。
3. 任务完成时间越早且路径越短，获得的评分（收益）越高；超时未完成则扣分。
4. 当车辆当前电量不足以到达下一目标点或回仓时，寻找最近或最优的充电站进行补能。
5. 需考虑充电站的排队与负荷压力。
6. 可以选择是否多辆车可以协同完成同一任务。
7. 完成至少两种新能源车辆调度策略，例如最近任务优先、最大任务优先。
8. 至少模拟三种以上不同大小规模的问题。
9. 有能力的同学可以尝试使用强化学习、超启发式、元启发式、多智能体方法等进阶算法，或在上帝视角下建立数学模型并调用 Gurobi/CPLEX 等精确求解器进行对比。
10. 图形界面展示加分。

## 已完成任务对照

| 要求 | 完成情况 |
| --- | --- |
| 使用图结构实现道路和寻路。 | 已完成。`Engine/Framework/core/graph.py` 使用邻接表建模道路网络，`Engine/Framework/core/pathfinder.py` 实现 Dijkstra 最短路、距离缓存和电量可达性检查。 |
| 1. 车辆数量有限，车辆具有电量上限和载重上限，系统模拟一段时间内动态出现的任务。 | 已完成。`Engine/Framework/core/entities.py` 定义车辆电量、载重、状态等属性，`Engine/Framework/core/simulation.py` 负责离散时间仿真、车辆状态更新和动态任务释放。 |
| 2. 每个任务包含产生时间、地点坐标和货物重量。 | 已完成。`Engine/Framework/generator/task_generator.py` 支持随机任务生成，`Engine/Framework/generator/real_task_generator.py` 支持在广州番禺区真实道路节点上生成动态任务，任务包含释放时间、截止时间、节点坐标位置和货物重量。 |
| 3. 任务完成越早且路径越短收益越高，超时未完成扣分。 | 已完成。仿真核心在任务完成、等待时间、行驶距离和超时状态上进行记录与评分，日志输出包含 `task_log`、`vehicle_log`、`step_log` 等结果。 |
| 4. 电量不足时寻找最近或最优充电站补能。 | 已完成。系统支持 `nearest_station` 和 `optimal_station` 两种充电策略，并在派单和执行过程中检查车辆是否能够完成任务并回仓。 |
| 5. 考虑充电站排队与负荷压力。 | 已完成。`ChargingStation` 记录充电桩占用、排队车辆和负荷状态，仿真日志输出 `station_log` 用于分析充电站拥堵。 |
| 6. 可选择是否多辆车协同完成同一任务。 | 已完成。`simulation.py` 支持协同任务分配接口，并提供协同任务比例与自动协同调度开关。 |
| 7. 至少完成两种新能源车辆调度策略。 | 已完成。已实现 `nearest` 最近任务优先、`heaviest` 最大重量优先、`earliest_deadline` 最早截止时间优先三种在线启发式调度策略。 |
| 8. 至少模拟三种以上不同大小规模的问题。 | 已完成。配置和脚本支持 `small`、`medium`、`large` 三种规模，并可通过 `run_all_experiments.sh` 批量运行对比实验。 |
| 广州番禺区实地数据测试。 | 已完成。项目保留 `Engine/Map Resource/panyu.osm.pbf` 和 `Engine/Map Resource/processed/panyu/`，processed 数据包含 131276 个真实道路节点、142593 条边和 57 个充电站；`Engine/Framework/examples/run_panyu_processed_baseline.py` 与 `Engine/Framework/configs/panyu_processed_baseline.yaml` 可直接在番禺真实路网上运行调度测试。 |
| 9.1 进阶算法：强化学习、超启发式、元启发式、多智能体等。 | 已完成强化学习方向。`policy/gymnasium_qlearning/` 实现 Gymnasium 环境、状态编码、启发式动作集合和 tabular Q-learning 训练流程。 |
| 9.2 上帝视角精确求解：建立数学模型并调用 Gurobi/CPLEX 等求全局最优，再与动态策略对比。 | 已完成离线 MILP 基线。`policy/offline/god_view_milp.py` 建立小规模上帝视角调度模型，可作为在线策略的全局上界/近似最优对照。 |
| 图形界面展示加分。 | 已完成。`UI/logistics-ui/` 基于 Next.js + TypeScript 实现可视化界面，展示车辆、任务、充电站、地图和实时统计信息；`Engine/Framework/api/server.py` 提供 FastAPI/WebSocket 后端。 |

## 完整运行步骤

### 1. 准备 Python 和前端依赖

在仓库根目录执行：

```bash
conda create -n datastructure python=3.10 -y
conda activate datastructure
pip install -r requirements.txt
```

安装前端依赖：

```bash
cd UI/logistics-ui
npm install
cd ../..
```

如果直接从仓库根目录运行 Python 模块，建议设置：

```bash
export PYTHONPATH="$PWD/Engine:$PWD"
```

`run_all_experiments.sh` 会自动设置 `PYTHONPATH`。

### 2. 启动后端服务

终端 1：

```bash
cd Engine
python -m uvicorn Framework.api.server:app --host 127.0.0.1 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

后端会优先加载 `Engine/Map Resource/processed/panyu/` 下的广州番禺真实路网数据；如果 processed 数据不存在，则回退到随机地图。

### 3. 启动前端界面

终端 2：

```bash
cd UI/logistics-ui
npm run dev
```

浏览器打开：

```text
http://localhost:3000
```

如果要连接后端仿真服务，在 `UI/logistics-ui/.env.local` 中配置：

```bash
NEXT_PUBLIC_USE_ENGINE_BACKEND=1
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_AMAP_KEY=你的高德 Web JSAPI Key
NEXT_PUBLIC_AMAP_SECURITY_CODE=你的高德安全密钥
```

如果没有高德 Key，前端仍可使用本地 Canvas 视图进行展示。

### 4. 运行随机地图基线实验

```bash
cd Engine
python -m Framework.examples.run_baseline \
  --scale small \
  --scheduler nearest \
  --charging-strategy optimal_station \
  --out ../experiments/test/small_nearest
cd ..
```

支持的调度策略：

- `nearest`
- `earliest_deadline`
- `heaviest`

支持的充电策略：

- `optimal_station`
- `nearest_station`

### 5. 运行广州番禺区真实路网实验

项目包含广州番禺区 processed 实地数据：

- `Engine/Map Resource/panyu.osm.pbf`
- `Engine/Map Resource/processed/panyu/nodes.parquet`
- `Engine/Map Resource/processed/panyu/edges.parquet`
- `Engine/Map Resource/processed/panyu/stations.parquet`
- `Engine/Map Resource/processed/panyu/meta.json`

processed 数据规模：

- 131276 个真实道路节点
- 142593 条道路边
- 57 个充电站

运行默认番禺配置：

```bash
cd Engine
python -m Framework.examples.run_panyu_processed_baseline \
  --config "Framework/configs/panyu_processed_baseline.yaml"
cd ..
```

也可以覆盖配置：

```bash
cd Engine
python -m Framework.examples.run_panyu_processed_baseline \
  --config "Framework/configs/panyu_processed_baseline.yaml" \
  --scheduler heaviest \
  --vehicles 10 \
  --tasks 120 \
  --horizon 360
cd ..
```

### 6. 训练 Q-learning 策略

```bash
PYTHONPATH="$PWD/Engine:$PWD" python -m policy.gymnasium_qlearning.train_q_learning \
  --scale small \
  --episodes 200 \
  --max-steps 180 \
  --seed 7 \
  --out-dir experiments/qlearning/small
```

混合规模训练：

```bash
PYTHONPATH="$PWD/Engine:$PWD" python -m policy.gymnasium_qlearning.train_q_learning \
  --scale small \
  --train-scales small medium \
  --episodes 300 \
  --max-steps 300 \
  --seed 7 \
  --out-dir experiments/qlearning/mixed
```

### 7. 运行离线 MILP 基线

```bash
PYTHONPATH="$PWD/Engine:$PWD" python -m policy.offline.god_view_milp \
  --scale small \
  --solver gurobi \
  --time-limit 120 \
  --out experiments/milp/small_gurobi
```

如果没有 Gurobi，可安装 `pulp` 并按本机求解器情况调整：

```bash
pip install pulp
```

### 8. 批量运行实验

```bash
chmod +x run_all_experiments.sh
./run_all_experiments.sh
```

批量脚本会运行多规模启发式基线、Q-learning、充电策略消融和可选 MILP。生成结果默认写入 `experiments/`。
