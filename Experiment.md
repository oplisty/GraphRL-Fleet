# 实验设计方案

本文档基于当前 Engine 框架与 policy 模块的实现能力，结合论文需求，设计完整的对比实验与消融实验方案。

---

## 0. 实验运行环境说明

### 0.1 工作目录
**所有实验脚本必须从项目根目录运行**：
```bash
cd /Users/oplisty/Desktop/数据结构大作业/Data-Structure-HW
```

### 0.2 Python 环境
确保激活 conda 环境：
```bash
conda activate datastructure
```

### 0.3 依赖检查
```bash
# 基础依赖（应该已安装）
pip install gymnasium numpy

# MILP 实验额外依赖
pip install pulp

# Gurobi 求解器（需要 license）
# 如果没有 Gurobi license，可以用 CPLEX 或跳过 MILP 实验
```

### 0.4 目录结构确认
```bash
# 确认当前在项目根目录
pwd
# 应该输出：/Users/oplisty/Desktop/数据结构大作业/Data-Structure-HW

# 确认关键目录存在
ls Engine/Framework/examples/
ls policy/gymnasium_qlearning/
ls policy/offline/
```

---

## 1. 当前 Engine 集成的实验能力

### 1.1 已实现的基线调度器
位置：`Engine/Framework/scheduler/`

- **NearestTaskScheduler**：最近任务优先（贪心距离）
- **EarliestDeadlineScheduler**：最早截止时间优先（EDF）
- **HeaviestTaskScheduler**：最大重量任务优先
- **OfflinePlanScheduler / OfflineRouteScheduler**：离线规划回放

### 1.2 已实现的充电策略
位置：`Engine/Framework/core/config.py` + `simulation.py`

- **optimal_station**：综合距离、排队长度、充电桩占用数选站
- **nearest_station**：仅按最短路距离选站

### 1.3 已实现的实验脚本
位置：`Engine/Framework/examples/`

- `run_baseline.py`：单次基线运行（支持 small/medium/large + 3 种 scheduler + 2 种充电策略）
- `run_experiment_matrix.py`：批量矩阵实验（random map + Panyu processed map）
- `run_panyu_processed_baseline.py`：真实番禺地图基线
- `run_offline_plan_replay.py`：离线 MILP 方案回放

### 1.4 已实现的 Q-learning 超启发式
位置：`policy/gymnasium_qlearning/`

- **事件驱动 Gymnasium 环境**：在任务发布、任务完成、到达充电站、充电结束、车辆空闲等事件点触发决策
- **统一规则库**：6 条规则（nearest+best_charge, edf+best_charge, max_weight+best_charge, best_score+best_charge, nearest+nearest_charge, best_score+nearest_charge）
- **表格型 Q-learning**：支持多规模训练、early stopping、checkpoint、评估

### 1.5 已实现的离线 MILP
位置：`policy/offline/god_view_milp.py`

- **上帝视角 MILP**：Gurobi/CPLEX 求解器
- **支持分段充电建模**：piecewise / linear
- **自动降级机制**：license 受限时自动降规模

---

## 2. 对比实验设计（Comparative Experiments）

### 2.1 实验目标
验证 Q-learning 超启发式相对于固定启发式基线与离线 MILP 的性能优势与适用场景。

### 2.2 对比方法

#### 2.2.1 固定启发式基线（Heuristic Baselines）
- **Nearest-First (NF)**：最近任务优先 + 最优充电站
- **Earliest-Deadline-First (EDF)**：最早截止优先 + 最优充电站
- **Heaviest-First (HF)**：最大重量优先 + 最优充电站

#### 2.2.2 Q-learning 超启发式（Q-HH）
- **Q-HH-Small**：在 small 规模上训练 200 episodes
- **Q-HH-Medium**：在 medium 规模上训练 300 episodes
- **Q-HH-Mixed**：在 small+medium 混合规模上训练 300 episodes（轮换）

#### 2.2.3 离线 MILP 上界（Offline Upper Bound）
- **MILP-Gurobi**：使用 Gurobi 求解器，time_limit=120s
- 仅在 small 规模上运行（作为理论上界参考）

### 2.3 实验场景

#### 2.3.1 规模维度
- **Small**：5 车 30 任务 2 充电站 180 步
- **Medium**：10 车 100 任务 4 充电站 300 步
- **Large**：20 车 300 任务 8 充电站 480 步

#### 2.3.2 地图类型
- **Random Map**：随机生成路网（用于训练与泛化测试）
- **Panyu Processed Map**：真实番禺地图（用于实际场景验证）

#### 2.3.3 随机种子
每个配置运行 5 个不同随机种子（seed=7,8,9,10,11），报告均值与标准差

### 2.4 评价指标
- **Final Score**：综合得分（越高越好）
- **Completed Tasks**：完成任务数（越高越好）
- **Expired Tasks**：过期任务数（越低越好）
- **Total Distance**：总行驶距离（越低越好）
- **Charging Sessions**：充电次数（越低越好）
- **Avg Charge Wait**：平均充电排队时间（越低越好）

### 2.5 实验执行脚本

#### 2.5.1 训练 Q-learning 模型
```bash
# Small 规模训练
python -m policy.gymnasium_qlearning.train_q_learning \
  --scale small \
  --episodes 200 \
  --max-steps 180 \
  --seed 7 \
  --out-dir experiments/qlearning/small

# Medium 规模训练
python -m policy.gymnasium_qlearning.train_q_learning \
  --scale medium \
  --episodes 300 \
  --max-steps 300 \
  --seed 7 \
  --out-dir experiments/qlearning/medium

# Mixed 规模训练
python -m policy.gymnasium_qlearning.train_q_learning \
  --scale small \
  --train-scales small medium \
  --episodes 300 \
  --max-steps 300 \
  --seed 7 \
  --out-dir experiments/qlearning/mixed
```

#### 2.5.2 运行基线对比
```bash
# 批量运行所有基线（random map）
for scale in small medium large; do
  for scheduler in nearest earliest_deadline heaviest; do
    for seed in 7 8 9 10 11; do
      python -m Engine.Framework.examples.run_baseline \
        --scale $scale \
        --scheduler $scheduler \
        --charging-strategy optimal_station \
        --seed $seed \
        --out experiments/baselines/${scale}_${scheduler}_seed${seed}
    done
  done
done
```

#### 2.5.3 运行 MILP 上界（仅 small）
```bash
# 需要在 Engine 根目录运行
python -m policy.offline.god_view_milp \
  --scale small \
  --solver gurobi \
  --time-limit 120 \
  --out experiments/milp/small_gurobi
```

---

## 3. 消融实验设计（Ablation Studies）

### 3.1 实验目标
验证系统关键组件对性能的贡献，包括充电策略、事件驱动决策、规则库设计、训练规模等。

### 3.2 消融维度

#### 3.2.1 充电策略消融（Charging Strategy Ablation）
**目标**：验证"最优充电站"相对于"最近充电站"的性能提升

**对比组**：
- **Baseline-Optimal**：Nearest-First + optimal_station
- **Baseline-Nearest**：Nearest-First + nearest_station
- **Q-HH-Optimal**：Q-learning + optimal_station
- **Q-HH-Nearest**：Q-learning + nearest_station

**场景**：Small + Medium 规模，各 5 个随机种子

**执行脚本**：
```bash
# 基线对比
for strategy in optimal_station nearest_station; do
  for seed in 7 8 9 10 11; do
    python -m Engine.Framework.examples.run_baseline \
      --scale medium \
      --scheduler nearest \
      --charging-strategy $strategy \
      --seed $seed \
      --out experiments/ablation/charging/${strategy}_seed${seed}
  done
done

# Q-learning 对比
for strategy in optimal_station nearest_station; do
  python -m policy.gymnasium_qlearning.train_q_learning \
    --scale medium \
    --episodes 200 \
    --charging-strategy $strategy \
    --seed 7 \
    --out-dir experiments/ablation/qlearning_charging/${strategy}
done
```

#### 3.2.2 规则库设计消融（Rule Library Ablation）
**目标**：验证统一规则库中不同规则组合的必要性

**对比组**：
- **Full-6-Rules**：完整 6 条规则（当前默认）
- **Task-Only-4-Rules**：仅任务规则（nearest, edf, max_weight, best_score）+ 固定 optimal_station
- **Charge-Only-2-Rules**：固定 nearest 任务规则 + 2 种充电策略

**场景**：Medium 规模，训练 200 episodes

**实现方式**：需要在 `policy/gymnasium_qlearning/heuristics.py` 中临时调整 `RULE_LIBRARY`

#### 3.2.3 训练规模消融（Training Scale Ablation）
**目标**：验证在不同规模上训练对泛化能力的影响

**对比组**：
- **Train-Small-Test-Small**：在 small 上训练，在 small 上测试
- **Train-Small-Test-Medium**：在 small 上训练，在 medium 上测试（泛化）
- **Train-Medium-Test-Medium**：在 medium 上训练，在 medium 上测试
- **Train-Mixed-Test-Medium**：在 small+medium 混合训练，在 medium 上测试

**场景**：训练 200 episodes，测试 10 个随机种子

**执行脚本**：
```bash
# 训练阶段
python -m policy.gymnasium_qlearning.train_q_learning \
  --scale small \
  --episodes 200 \
  --seed 7 \
  --out-dir experiments/ablation/scale/train_small

python -m policy.gymnasium_qlearning.train_q_learning \
  --scale medium \
  --episodes 200 \
  --seed 7 \
  --out-dir experiments/ablation/scale/train_medium

python -m policy.gymnasium_qlearning.train_q_learning \
  --scale small \
  --train-scales small medium \
  --episodes 200 \
  --seed 7 \
  --out-dir experiments/ablation/scale/train_mixed

# 测试阶段（需要加载训练好的 Q 表并评估）
# 当前框架支持 evaluate_policy，可扩展为跨规模评估
```

#### 3.2.4 事件驱动决策消融（Event-Driven Decision Ablation）
**目标**：验证事件驱动决策相对于固定步长决策的优势

**对比组**：
- **Event-Driven**：当前实现（在事件点决策）
- **Fixed-Step**：每 N 步决策一次（需要回退到之前版本或新增配置）

**场景**：Medium 规模，训练 200 episodes

**实现方式**：需要在 `policy/gymnasium_qlearning/env.py` 中新增 `decision_mode` 配置

---

## 4. 实验输出与分析

### 4.1 输出文件结构
```
experiments/
├── baselines/
│   ├── small_nearest_seed7/
│   │   ├── events.json
│   │   ├── vehicle_log.json
│   │   ├── task_log.json
│   │   └── summary.json
│   └── ...
├── qlearning/
│   ├── small/
│   │   ├── q_table.json
│   │   ├── train_history.csv
│   │   ├── eval_summary.csv
│   │   └── training_summary.json
│   └── ...
├── milp/
│   └── small_gurobi/
│       ├── solution.json
│       └── summary.json
└── ablation/
    ├── charging/
    ├── scale/
    └── ...
```

### 4.2 结果汇总脚本
需要新增一个 `experiments/summarize_results.py`，用于：
- 读取所有实验输出
- 计算均值、标准差
- 生成对比表格（CSV + Markdown）
- 生成训练曲线图（matplotlib）

### 4.3 论文图表
- **Table 1**：对比实验主表（方法 × 规模 × 指标）
- **Table 2**：消融实验汇总表
- **Figure 1**：Q-learning 训练曲线（Total Reward + Eval Score）
- **Figure 2**：充电策略对比柱状图
- **Figure 3**：规模泛化性能对比

---

## 5. 实验执行时间估算

### 5.1 基线实验
- 单次运行：~1-5 分钟（取决于规模）
- 总计：3 规模 × 3 scheduler × 5 seed = 45 次 → **约 2-4 小时**

### 5.2 Q-learning 训练
- Small 200 episodes：~30-60 分钟
- Medium 300 episodes：~2-4 小时
- Mixed 300 episodes：~2-4 小时
- 总计：**约 5-9 小时**

### 5.3 MILP 求解
- Small 规模 120s time_limit：~2-3 分钟
- 总计：**约 10 分钟**

### 5.4 消融实验
- 充电策略：~1 小时
- 规则库：~2 小时
- 训练规模：~3 小时
- 总计：**约 6 小时**

**总实验时间估算：15-20 小时**（可并行加速）

---

## 6. 实验检查清单

- [ ] 确认所有基线脚本可正常运行
- [ ] 确认 Q-learning 训练脚本可正常运行
- [ ] 确认 MILP 求解器可用（Gurobi license）
- [ ] 准备实验输出目录结构
- [ ] 编写结果汇总脚本
- [ ] 运行对比实验（基线 + Q-learning + MILP）
- [ ] 运行消融实验（充电策略 + 规则库 + 训练规模）
- [ ] 生成实验表格与图表
- [ ] 撰写实验结果分析章节
- [ ] 检查论文图表与实验数据一致性

---

## 7. 后续扩展建议

### 7.1 短期扩展
- 新增协同任务场景实验（`collaborative_task_ratio > 0`）
- 新增 Panyu 真实地图对比实验
- 新增训练收敛性分析（Q 表热力图、动作分布）

### 7.2 中期扩展
- 实现 DQN / PPO 深度强化学习基线
- 实现在线学习与迁移学习实验
- 实现多目标优化实验（Pareto 前沿）

### 7.3 长期扩展
- 实现分布式训练与大规模场景
- 实现实时可视化与交互式调试
- 实现与真实物流系统对接

---

## 附录：关键配置参数

### A.1 场景配置（`Engine/Framework/core/config.py`）
```python
# Small
num_vehicles=5, num_tasks=30, num_stations=2, num_road_nodes=25, 
map_width=30, map_height=30, horizon=180

# Medium
num_vehicles=10, num_tasks=100, num_stations=4, num_road_nodes=60,
map_width=50, map_height=50, horizon=300

# Large
num_vehicles=20, num_tasks=300, num_stations=8, num_road_nodes=120,
map_width=80, map_height=80, horizon=480
```

### A.2 Q-learning 配置（`policy/gymnasium_qlearning/q_learning.py`）
```python
alpha=0.1, gamma=0.95, epsilon=0.2, 
epsilon_decay=0.995, epsilon_min=0.05
```

### A.3 奖励函数（`policy/gymnasium_qlearning/env.py`）
```python
reward = delta_score
reward += 20.0 * delta_completed
reward -= 0.1 * delta_distance
reward -= 5.0 * delta_expired
reward -= 2.0 * emergency_unserved
reward -= 0.5 * delta_charge_starts
```
