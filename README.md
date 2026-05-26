# Dynamic Collaborative Scheduling System for New Energy Logistics Fleets Based on Graph Algorithms and Reinforcement Learning

A research-oriented repository for dynamic scheduling of new energy logistics fleets, featuring a graph-based simulation engine, Guangzhou Panyu district real road-network data, online heuristic and Q-learning policies, an offline MILP baseline, a FastAPI backend, and a web visualization frontend.

Chinese documentation: [README.zh-CN.md](README.zh-CN.md)

---

## Abstract

With the rapid growth of urban instant delivery, scheduling for new energy logistics fleets faces increasing challenges from dynamic task arrivals, limited vehicle resources, and complex charging constraints. This repository implements a dynamic collaborative scheduling system based on graph modeling and intelligent decision methods. The urban road network is represented as a weighted graph, and a discrete-time simulation framework is built by considering battery limits, load capacity, task deadlines, and charging-station congestion.

For path planning and reachability analysis, the system supports graph-based search and shortest-path utilities, while at the scheduling level it implements several heuristic strategies, including nearest-task-first, maximum-weight-first, earliest-deadline-first, and a Q-learning-based hyper-heuristic. In addition, an offline MILP module under full-information settings is developed for small-scale cases to generate near-optimal solutions and provide a baseline for comparison with online scheduling strategies.

The whole project follows a **simulation engine + backend + visualization frontend** architecture. It can be used for course demonstrations, algorithm experiments, ablation studies, real-map Panyu experiments, and reproducible scheduling comparisons. The repository is especially suitable for studying how dynamic tasks, battery constraints, charging queues, and online decision rules interact in new energy urban delivery scenarios.

---

## Repository Highlights

- Graph-based urban logistics simulation engine
- Guangzhou Panyu district OSM/PBF and processed real road-network data
- Dynamic task release and deadline-aware scheduling
- Vehicle battery, load, return-to-depot, and charging constraints
- Charging-station queue and occupancy modeling
- Online heuristic baselines and Q-learning hyper-heuristic
- Offline MILP small-scale exact/near-optimal baseline
- FastAPI realtime backend for simulation serving
- Next.js frontend for map-based visualization and demonstrations
- Experiment scripts for baselines, ablations, and result visualization

---

## Repository Structure

```text
Data-Structure-HW/
├── Engine/                          # Core simulation engine, backend, maps, experiment scripts
│   ├── Framework/
│   │   ├── api/                     # FastAPI + websocket backend
│   │   ├── configs/                 # YAML experiment and baseline configs
│   │   ├── core/                    # Graph, entities, logger, pathfinder, simulation kernel
│   │   ├── examples/                # Runnable experiment/baseline entrypoints
│   │   ├── generator/               # Random/real map and task generation
│   │   └── scheduler/               # Heuristic and offline replay schedulers
│   ├── Map Resource/                # Guangzhou Panyu real map data and preprocessing assets
├── UI/
│   └── logistics-ui/                # Next.js visualization frontend
├── policy/
│   ├── gymnasium_qlearning/         # Event-driven Gymnasium + tabular Q-learning
│   └── offline/                     # Offline MILP baseline
├── experiments/                     # Plotting scripts and generated experiment outputs
├── README.zh-CN.md                  # Chinese documentation
├── requirements.txt                 # Root Python dependencies
└── run_all_experiments.sh           # Batch experiment launcher
```

---

## Quickstart

### 1. Clone the repository

```bash
git clone https://github.com/oplisty/Data-Structure-HW.git
cd Data-Structure-HW
```

### 2. Create the Python environment

Recommended: Python 3.10 with Conda.

```bash
conda create -n datastructure python=3.10 -y
conda activate datastructure
pip install -r requirements.txt
```

If you want to run the frontend:

```bash
cd UI/logistics-ui
npm install
cd ../..
```

### 3. Run a quick baseline simulation

```bash
cd Engine
python -m Framework.examples.run_baseline \
  --scale small \
  --scheduler nearest \
  --charging-strategy optimal_station \
  --out ../experiments/test/small_nearest
cd ..
```

### 4. Train a quick Q-learning model

```bash
PYTHONPATH="$PWD/Engine:$PWD" python -m policy.gymnasium_qlearning.train_q_learning \
  --scale small \
  --episodes 50 \
  --max-steps 180 \
  --out-dir experiments/qlearning/quickstart
```

---

## Environment Setup

### Python dependencies

The root `requirements.txt` covers the current integrated workflow:

- `gymnasium`, `numpy` for RL training
- `fastapi`, `uvicorn`, `websockets` for backend serving
- `pyyaml` for configuration loading
- `pandas`, `pyarrow`, `fastparquet` for data processing
- `geopandas`, `shapely`, `pyproj`, `osmium` for map processing

Install them with:

```bash
pip install -r requirements.txt
```

### Optional solver dependency for MILP

The offline MILP baseline depends on `pulp`, and if you want Gurobi-based solving you also need a valid Gurobi installation/license.

```bash
pip install pulp
```

### Frontend environment variables

Create `UI/logistics-ui/.env.local` if you want backend-connected visualization:

```bash
NEXT_PUBLIC_USE_ENGINE_BACKEND=1
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_AMAP_KEY=your_amap_key
NEXT_PUBLIC_AMAP_SECURITY_CODE=your_amap_security_code
```

If AMap keys are not available, the frontend can still fall back to a local canvas view for development and demonstration.

---

## Full Run Guide

### 1. Prepare Python and frontend dependencies

From the repository root:

```bash
conda create -n datastructure python=3.10 -y
conda activate datastructure
pip install -r requirements.txt
```

Install frontend dependencies:

```bash
cd UI/logistics-ui
npm install
cd ../..
```

For direct Python module commands from the repository root, set:

```bash
export PYTHONPATH="$PWD/Engine:$PWD"
```

The batch script already sets `PYTHONPATH` internally.

### 2. Run the backend service

Open terminal 1:

```bash
cd Engine
python -m uvicorn Framework.api.server:app --host 127.0.0.1 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

The backend prefers the processed Guangzhou Panyu real map if `Engine/Map Resource/processed/panyu/` exists, and falls back to a random map otherwise.

### 3. Run the frontend visualization

Open terminal 2:

```bash
cd UI/logistics-ui
npm run dev
```

Open:

```text
http://localhost:3000
```

For backend-connected visualization, create `UI/logistics-ui/.env.local`:

```bash
NEXT_PUBLIC_USE_ENGINE_BACKEND=1
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_AMAP_KEY=your_amap_key
NEXT_PUBLIC_AMAP_SECURITY_CODE=your_amap_security_code
```

If no AMap key is provided, the UI can still use the local canvas fallback for demonstration.

### 4. Run a random-map baseline

```bash
cd Engine
python -m Framework.examples.run_baseline \
  --scale small \
  --scheduler nearest \
  --charging-strategy optimal_station \
  --out ../experiments/test/small_nearest
cd ..
```

Supported schedulers:

- `nearest`
- `earliest_deadline`
- `heaviest`

Supported charging strategies:

- `optimal_station`
- `nearest_station`

### 5. Run the Guangzhou Panyu real-map baseline

The repository includes processed Guangzhou Panyu road-network data:

- `Engine/Map Resource/panyu.osm.pbf`
- `Engine/Map Resource/processed/panyu/nodes.parquet`
- `Engine/Map Resource/processed/panyu/edges.parquet`
- `Engine/Map Resource/processed/panyu/stations.parquet`
- `Engine/Map Resource/processed/panyu/meta.json`

The processed Panyu dataset contains 131276 road nodes, 142593 edges, and 57 charging stations.

Run:

```bash
cd Engine
python -m Framework.examples.run_panyu_processed_baseline \
  --config "Framework/configs/panyu_processed_baseline.yaml"
cd ..
```

You can override the YAML settings from the command line, for example:

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

### 6. Run Q-learning training

```bash
PYTHONPATH="$PWD/Engine:$PWD" python -m policy.gymnasium_qlearning.train_q_learning \
  --scale small \
  --episodes 200 \
  --max-steps 180 \
  --seed 7 \
  --out-dir experiments/qlearning/small
```

Mixed-scale training:

```bash
PYTHONPATH="$PWD/Engine:$PWD" python -m policy.gymnasium_qlearning.train_q_learning \
  --scale small \
  --train-scales small medium \
  --episodes 300 \
  --max-steps 300 \
  --seed 7 \
  --out-dir experiments/qlearning/mixed
```

### 7. Run the offline MILP baseline

```bash
PYTHONPATH="$PWD/Engine:$PWD" python -m policy.offline.god_view_milp \
  --scale small \
  --solver gurobi \
  --time-limit 120 \
  --out experiments/milp/small_gurobi
```

If Gurobi is unavailable, install and use the supported open-source fallback where applicable:

```bash
pip install pulp
```

### 8. Run the full experiment batch

```bash
chmod +x run_all_experiments.sh
./run_all_experiments.sh
```

This runs:

- multi-scale heuristic baselines
- Q-learning training
- charging-strategy ablations
- optional MILP baseline

Generated outputs are written under `experiments/`.

---

## Core Functionalities and How to Run Them

## 1. Simulation engine baselines

The engine supports multiple online heuristic schedulers under unified logistics constraints.

### Supported baseline schedulers

- `nearest` — nearest-task-first
- `earliest_deadline` — earliest-deadline-first
- `heaviest` — maximum-weight-first

### Supported charging strategies

- `optimal_station`
- `nearest_station`

### Run one baseline

```bash
cd Engine
python -m Framework.examples.run_baseline \
  --scale medium \
  --scheduler earliest_deadline \
  --charging-strategy optimal_station \
  --out ../experiments/baselines/medium_edf
cd ..
```

This writes structured logs such as:

- `events.json/csv`
- `vehicle_log.json/csv`
- `task_log.json/csv`
- `station_log.json/csv`
- `step_log.json/csv`

---

## 2. Real-map and processed-map baselines

The repository includes Panyu map resources and processed data for more realistic experiments.

### Run processed Panyu baseline

```bash
cd Engine
python -m Framework.examples.run_panyu_processed_baseline \
  --config "Framework/configs/panyu_processed_baseline.yaml"
```

### Run experiment matrix

```bash
cd Engine
python -m Framework.examples.run_experiment_matrix \
  --config "Framework/configs/experiment_matrix.yaml"
```

This is useful for generating multi-scenario comparisons across random maps and real processed maps.

---

## 3. Q-learning hyper-heuristic training

The repository provides an event-driven Gymnasium environment where decisions are triggered at key logistics events such as:

- task release
- task completion
- arrival at charging station
- charging finish
- vehicle becoming idle

The Q-learning module selects from a unified rule library rather than hard-coding one fixed scheduler.

### Run Q-learning training

```bash
PYTHONPATH="$PWD/Engine:$PWD" python -m policy.gymnasium_qlearning.train_q_learning \
  --scale small \
  --episodes 200 \
  --max-steps 180 \
  --seed 7 \
  --out-dir experiments/qlearning/small
```

### Mixed-scale training

```bash
PYTHONPATH="$PWD/Engine:$PWD" python -m policy.gymnasium_qlearning.train_q_learning \
  --scale small \
  --train-scales small medium \
  --episodes 300 \
  --max-steps 300 \
  --seed 7 \
  --out-dir experiments/qlearning/mixed
```

### Q-learning outputs

Typical outputs include:

- `q_table.json`
- `train_history.json/csv`
- `eval_summary.json/csv`
- `training_summary.json`
- `training_config.json`
- `checkpoints/`

---

## 4. Offline MILP baseline

The offline solver provides a full-information small-scale baseline for comparison against online heuristics and learned policies.

### Run offline MILP

```bash
PYTHONPATH="$PWD/Engine:$PWD" python -m policy.offline.god_view_milp \
  --scale small \
  --solver gurobi \
  --time-limit 120 \
  --out experiments/milp/small_gurobi
```

If `gurobi` is unavailable, you may need to adapt the solver path or install the solver backend described in `policy/offline/god_view_milp.py`.

This baseline is intended primarily for:

- small-scale near-optimal comparison
- validating the online scheduler gap
- oracle-style references for experiment comparison

---

## 5. Backend serving

The backend exposes the engine through FastAPI and realtime updates.

### Start backend

```bash
cd Engine
python -m uvicorn Framework.api.server:app --host 127.0.0.1 --port 8000
```

### Health check

```bash
curl http://127.0.0.1:8000/api/v1/health
```

The backend is used by the frontend for visualization and by interactive demos during presentation.

---

## 6. Frontend visualization

The web UI provides:

- map rendering
- vehicle/task/station panels
- statistics and event logs
- strategy controls
- realtime backend connection

### Start frontend

```bash
cd UI/logistics-ui
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

For backend-connected mode, ensure the backend is already running and `.env.local` is configured.

---

## 7. Batch experiment execution

The repository includes a batch runner for reproducing the main baseline, Q-learning, charging-ablation, and optional MILP experiments.

### Run all experiments

```bash
chmod +x run_all_experiments.sh
./run_all_experiments.sh
```

The batch script includes:

- multi-scale heuristic baseline runs
- Q-learning training runs
- charging-strategy ablations
- optional MILP execution

It also prints colored progress information between experiments for easier terminal monitoring.

---

## Output and Reproducibility

Typical experiment outputs are stored under:

```text
experiments/
├── baselines/
├── qlearning/
├── ablation/
└── milp/
```

For result reporting, the most useful generated files are:

- final summaries from baseline runs
- RL training/evaluation curves
- MILP result summaries
- exported JSON/CSV logs

---

## Common Issues

### 1. `No module named Framework`

Run engine modules from the `Engine/` directory, use `run_all_experiments.sh`, or ensure `PYTHONPATH` contains:

- project root
- `Engine/`

The batch script already handles this.

### 2. `No module named policy`

This usually happens when running from the wrong working directory. Use the repository root and set `PYTHONPATH="$PWD/Engine:$PWD"` when running policy modules directly.

### 3. MILP solver import errors

Install:

```bash
pip install pulp
```

If Gurobi is still unavailable, the issue is likely solver installation or license related.

### 4. Frontend map not loading

Check `.env.local` and verify your AMap key / security code configuration.

---

## Project Scope

This repository is designed for:

- course project demonstrations
- scheduling strategy comparison
- graph-based logistics simulation
- reinforcement-learning-based heuristic selection
- small-scale exact optimization comparison

It is not a production dispatch system, but it is structured to support future extensions in multi-agent coordination, richer map integration, and stronger RL baselines.
