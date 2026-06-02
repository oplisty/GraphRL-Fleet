# Dynamic Collaborative Scheduling System for New Energy Logistics Fleets

<p align="center">
  <img src="Figure/图片 1.png" alt="System Framework" width="85%">
</p>

> **Graph-based simulation engine + Heuristic & RL scheduling + MILP offline baseline** — for dynamic new energy logistics fleet scheduling in urban road networks.

[中文文档](README.zh-CN.md)

---

## Abstract

With the rapid growth of urban instant delivery, scheduling for new energy logistics fleets faces increasing challenges from dynamic task arrivals, limited vehicle resources, and complex charging constraints. This repository implements a dynamic collaborative scheduling system based on graph modeling and intelligent decision methods. The urban road network is represented as a weighted graph, and a discrete-time simulation framework is built by considering battery limits, load capacity, task deadlines, and charging-station congestion.

The project follows a **simulation engine + backend + visualization frontend** architecture, supporting course demonstrations, algorithm experiments, ablation studies, and reproducible scheduling comparisons.

---

## Problem Setting

### Dynamic Task Model

Tasks arrive stochastically during the simulation horizon. Each task is defined by:

- **Release time** — the earliest time the task becomes available
- **Task node** — the delivery location on the road network
- **Cargo weight** — affects vehicle load capacity and energy consumption
- **Deadline** — tasks not completed before their deadline are counted as expired

### EV Fleet Model

Each new energy vehicle is modeled with realistic constraints:

- **Battery capacity** and unit-distance energy consumption
- **Load capacity** limiting how many tasks can be carried simultaneously
- **Charging time** proportional to the energy deficit
- **Return-to-depot** requirement

### Road Network

The urban road network is modeled as a weighted graph $G = (V, E)$:

| Node Type | Description |
|-----------|-------------|
| Task points | Delivery destinations with dynamic task arrivals |
| Charging stations | Recharging nodes with limited piles, occupancy, and queue status |
| Depot | Vehicle origin and return point |

Edge weights encode both **travel distance** and **energy cost**.

**Real map data**: Guangzhou Panyu district — 131,276 road nodes, 142,593 edges, and 57 charging stations extracted from OpenStreetMap.

---

## Framework

<p align="center">
  <img src="Figure/图片 1.png" alt="Architecture" width="90%">
</p>

The system follows a layered architecture:

| Layer | Components | Technology |
|-------|-----------|------------|
| **Engine** | Graph, entities, simulation kernel, pathfinder, logger | Python |
| **Policy** | Heuristic schedulers, Q-learning, offline MILP | Gymnasium, Gurobi/PuLP |
| **Service** | REST API + WebSocket realtime backend | FastAPI, Uvicorn |
| **UI** | Map visualization, vehicle/task/station panels, strategy controls | Next.js |

---

## Core Methods

### Path Planning

Find the feasible minimum-cost path under **energy feasibility** — a path is only executable if the vehicle has enough remaining battery.

| Algorithm | Type | Strength |
|-----------|------|----------|
| **Dijkstra** | Exact shortest path | Stable baseline for general graphs |
| **A\*** | Heuristic-accelerated | Fast searching for large-scale road networks |
| **RRT** | Sampling-based | Continuous space obstacle avoidance |

### Heuristic Scheduling Strategies

Three scoring-based schedulers operate under the same framework. At each decision point, the scheduler scores all pending tasks and assigns the top-ranked one.

| Strategy | Scoring Criterion | Strength | Weakness |
|----------|-------------------|----------|----------|
| **Nearest Task First (NTF)** | min travel distance | Fast response, low energy consumption | Ignores deadlines — distant urgent tasks risk expiration |
| **Earliest Deadline First (EDF)** | min slack time | Fewer expired tasks in small-scale | Ignores distance and battery — long trips cause cascading delays |
| **Maximum Weight First (MWF)** | max cargo weight | High value per trip, good for heavy-load scenarios | Ignores both distance and deadlines — weakest urgency response |

#### Simulation Demos

<p align="center">
  <table>
    <tr>
      <td align="center"><b>Nearest Task First</b></td>
      <td align="center"><b>Earliest Deadline First</b></td>
      <td align="center"><b>Maximum Weight First</b></td>
    </tr>
    <tr>
      <td>
        <video src="Figure/Nearest Task First.mp4" width="100%" controls muted autoplay loop></video>
      </td>
      <td>
        <video src="Figure/Earliest-Deadline-First .mp4" width="100%" controls muted autoplay loop></video>
      </td>
      <td>
        <video src="Figure/Maximum-Weight-First.mp4" width="100%" controls muted autoplay loop></video>
      </td>
    </tr>
  </table>
</p>

### Q-Learning Hyper-Heuristic

An event-driven Gymnasium environment where the agent selects from a unified rule library at each logistics event (task release, task completion, charging finish, vehicle idle, etc.).

**State representation** — four feature dimensions:

| State Feature | Description |
|---------------|-------------|
| Backlog | Accumulation level of unassigned tasks |
| Urgency | Time pressure of current task deadlines |
| Battery | Overall battery level of the fleet |
| Queue | Queuing and congestion status at charging stations |

**Action space**: select from {NTF, EDF, MWF, Charge-Nearest, Charge-Optimal}

<p align="center">
  <img src="Figure/Converge_curve.png" alt="Q-learning Convergence" width="55%">
</p>

### Offline MILP Baseline

Under full-information settings (all tasks known in advance), the problem is formulated as a mixed-integer linear program:

- **Task assignment**: each task served exactly once by one vehicle
- **Flow conservation**: vehicle routes must be continuous
- **Battery / SOC**: energy decreases with driving, increases with charging, never negative
- **Deadline**: lateness = arrival time − deadline
- **Capacity**: load along route ≤ vehicle capacity

Solved via Gurobi (recommended) or PuLP (open-source fallback). Serves as an **oracle baseline** for small-scale cases.

---

## Experiments

### Experiment Scales

| Scale | Vehicles | Tasks | Stations | Road Nodes | Map Size | Horizon |
|-------|----------|-------|----------|------------|----------|---------|
| Small | 5 | 30 | 2 | 25 | 30×30 | 180 |
| Medium | 10 | 100 | 4 | 60 | 50×50 | 300 |
| Large | 20 | 300 | 8 | 120 | 80×80 | 480 |

### Results

<p align="center">
  <img src="Figure/Comparison.png" alt="Strategy Comparison" width="80%">
</p>

<p align="center">
  <img src="Figure/Comparison2.png" alt="Ablation Results" width="80%">
</p>

### Key Findings

1. **Nearest Task First is the most robust** across all scales — simple distance-based dispatch generalizes well
2. **Q-learning outperforms individual heuristics in small-scale scenarios** — learned rule selection beats any single fixed strategy
3. **Charging strategies are more critical for learning-based methods** — the interaction between charging decisions and task scheduling is non-trivial

---

## Repository Structure

```text
GraphRL-Fleet/
├── Engine/                          # Core simulation engine, backend, maps, experiment scripts
│   ├── Framework/
│   │   ├── api/                     # FastAPI + WebSocket backend
│   │   ├── configs/                 # YAML experiment and baseline configs
│   │   ├── core/                    # Graph, entities, logger, pathfinder, simulation kernel
│   │   ├── examples/                # Runnable experiment/baseline entrypoints
│   │   ├── generator/               # Random/real map and task generation
│   │   └── scheduler/               # Heuristic and offline replay schedulers
│   └── Map Resource/                # Guangzhou Panyu real map data and preprocessing assets
├── UI/
│   └── logistics-ui/                # Next.js visualization frontend
├── policy/
│   ├── gymnasium_qlearning/         # Event-driven Gymnasium + tabular Q-learning
│   └── offline/                     # Offline MILP baseline
├── experiments/                     # Plotting scripts and generated experiment outputs
├── Figure/                          # Figures, charts, and demo videos
├── README.zh-CN.md                  # Chinese documentation
├── requirements.txt                 # Python dependencies
└── run_all_experiments.sh           # Batch experiment launcher
```

---

## Quick Start

### 1. Environment Setup

```bash
conda create -n datastructure python=3.10 -y
conda activate datastructure
pip install -r requirements.txt
```

Optional: install frontend dependencies and MILP solver

```bash
cd UI/logistics-ui && npm install && cd ../..
pip install pulp
```

### 2. Run a Baseline Simulation

```bash
cd Engine
python -m Framework.examples.run_baseline \
  --scale small \
  --scheduler nearest \
  --charging-strategy optimal_station \
  --out ../experiments/test/small_nearest
cd ..
```

Supported schedulers: `nearest`, `earliest_deadline`, `heaviest`
Supported charging strategies: `optimal_station`, `nearest_station`

### 3. Run Panyu Real-Map Baseline

```bash
cd Engine
python -m Framework.examples.run_panyu_processed_baseline \
  --config "Framework/configs/panyu_processed_baseline.yaml"
cd ..
```

### 4. Train Q-Learning

```bash
PYTHONPATH="$PWD/Engine:$PWD" python -m policy.gymnasium_qlearning.train_q_learning \
  --scale small \
  --episodes 200 \
  --max-steps 180 \
  --seed 7 \
  --out-dir experiments/qlearning/small
```

### 5. Run Offline MILP

```bash
PYTHONPATH="$PWD/Engine:$PWD" python -m policy.offline.god_view_milp \
  --scale small \
  --solver gurobi \
  --time-limit 120 \
  --out experiments/milp/small_gurobi
```

### 6. Launch Visualization

Terminal 1 — backend:

```bash
cd Engine
python -m uvicorn Framework.api.server:app --host 127.0.0.1 --port 8000
```

Terminal 2 — frontend:

```bash
cd UI/logistics-ui
npm run dev
```

Open `http://localhost:3000`. For backend-connected mode, configure `UI/logistics-ui/.env.local`:

```bash
NEXT_PUBLIC_USE_ENGINE_BACKEND=1
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_AMAP_KEY=your_amap_key
NEXT_PUBLIC_AMAP_SECURITY_CODE=your_amap_security_code
```

### 7. Batch Experiments

```bash
chmod +x run_all_experiments.sh
./run_all_experiments.sh
```

---

## Common Issues

| Problem | Solution |
|---------|----------|
| `No module named Framework` | Run from `Engine/` directory or set `PYTHONPATH` |
| `No module named policy` | Set `PYTHONPATH="$PWD/Engine:$PWD"` |
| MILP solver import error | `pip install pulp` (or install Gurobi) |
| Frontend map not loading | Check `.env.local` AMap key configuration |
| `PYTHONPATH` not set | The batch script `run_all_experiments.sh` sets it automatically |

---

## Project Scope

This repository is designed for:

- Course project demonstrations and algorithm experiments
- Scheduling strategy comparison under unified constraints
- Graph-based logistics simulation with real road-network data
- Reinforcement-learning-based heuristic selection
- Small-scale exact optimization comparison (MILP oracle)

It is not a production dispatch system, but is structured to support future extensions in multi-agent coordination, richer map integration, and stronger RL baselines.
