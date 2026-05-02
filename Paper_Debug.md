# Experiment（中文版写作规划）

## 1. 实验部分总体写作目标

本节的核心目标不是简单罗列运行结果，而是围绕“本文提出的方法是否有效、在什么条件下有效、相较于哪些基线更优、代价是什么”这几个问题展开系统性验证。按照 CVPR 风格的论文写法，实验部分应当围绕以下四个层次组织：

1. **实验设置（Experimental Setup）**：说明环境、规模、评价指标、对比方法与实现细节；
2. **主结果（Main Results）**：比较 baseline、Q-learning 超启发式与离线 MILP 的表现差异；
3. **消融分析（Ablation Study）**：分析奖励项、启发式动作库、充电策略等设计是否必要；
4. **定性分析（Qualitative Analysis）**：结合可视化回放、车辆路径与充电行为解释模型表现。

也就是说，Experiment 部分不应只回答“哪个方法分数高”，还要回答“为什么高”“在哪些场景下高”“离线最优与在线策略之间差距来自哪里”。

---

## 2. 建议的 Experiment 章节结构

建议论文中的 `Experiment` 章节采用如下结构：

### 4.1 Experimental Setup
这一小节用于回答“实验是如何搭建的”。建议包含以下内容：

#### 4.1.1 环境与场景设置
根据代码实现，当前实验环境可自然划分为 `small`、`medium`、`large` 三种规模，且 Q-learning 训练脚本中已支持通过 `--scale` 和 `--train-scales` 控制训练与评估规模。因此可在文中明确说明：
- `small`：用于快速训练与算法验证；
- `medium`：用于更复杂动态任务压力下的性能测试；
- `large`：用于验证方法扩展性与鲁棒性。

此外，还应说明环境中包含：
- 有限数量车辆；
- 动态释放任务；
- 电量上限与载重上限；
- 两种充电策略（`optimal_station` / `nearest_station`）；
- 任务截止时间与超时惩罚；
- 充电站排队与队列拥堵。

如果最终你们在报告中只保留两个规模，也建议在文中写清楚原因，例如：离线 MILP 受求解器规模限制，仅在 tiny/small 规模上做全局最优对比，而在线方法在 medium/large 上测试扩展能力。

#### 4.1.2 对比方法
根据当前代码，可以明确列出如下比较对象：

**启发式 baselines：**
- Nearest-task-first with best charging
- Earliest-deadline-first with best charging
- Max-weight-first with best charging
- Best-score heuristic with best charging
- Nearest-task-first with nearest-station charging
- Best-score heuristic with nearest-station charging

这些方法已经在 `policy/gymnasium_qlearning/heuristics.py` 中作为 `RULE_LIBRARY` 实现，因而完全可以在论文中定义为实验对比基线。

**强化学习方法：**
- Q-learning hyper-heuristic

该方法的动作空间并不是原始路径或任务编号，而是对上述底层启发式规则的选择，因此实验中要明确说明：Q-learning 是在统一仿真环境中学习“何时采用哪一种 rule”的高层策略选择器。

**离线优化上界：**
- Offline MILP planner

该方法在任务全集已知的上帝视角下求解全局计划，适合作为小规模问题上的近优参考上界，而不是大规模动态场景下的直接在线部署方案。

#### 4.1.3 评价指标
结合训练脚本 `train_q_learning.py`、环境封装 `env.py` 和输出字段，当前可直接写入论文的指标包括：

- **Final Score**：最终总得分，是最核心的综合指标；
- **Completed Tasks**：完成任务数量；
- **Expired Tasks**：超时任务数量；
- **Total Reward**：强化学习训练过程中的累计奖励；
- **Steps / Makespan**：完成调度过程所需时间步或离线求解中的整体完工时间；
- **Total Distance**：车辆总行驶距离；
- **Total Tardiness**：总迟到量（MILP 输出中已给出）；
- **Charging-related statistics**：如平均排队长度、充电触发次数或充电负载（若日志中已有，可进一步统计）。

论文写作时建议将指标分成两类：
1. **任务效能指标**：score、completed、expired、tardiness；
2. **运行成本指标**：distance、makespan、charging burden。

这样更符合 CVPR 风格中“effectiveness + efficiency/cost”的结果组织方式。

#### 4.1.4 实现细节
结合代码可写明如下实验细节：
- Q-learning 采用表格型 `Q-table`；
- 状态空间由五维离散状态组成：空闲车辆比例、任务积压程度、任务紧迫程度、低电量车辆比例、充电拥堵程度；
- 动作空间大小等于规则库大小，即当前为 6 个 unified rules；
- 默认训练超参数包括：`alpha=0.1`、`gamma=0.95`、`epsilon=0.2`、`epsilon_decay=0.995`、`epsilon_min=0.05`；
- 每轮训练后采用 greedy policy 做 `eval_episodes` 次评估；
- 训练日志保存 `episode`、`epsilon`、`final_score`、`completed_tasks`、`expired_tasks`、`eval_score_mean` 等字段。

如果最终报告中给出具体实验命令，可以把训练命令附在附录或实验设置小节最后，例如说明如何用 `--episodes`、`--scale`、`--train-scales` 控制训练方案。

---

## 3. 主实验结果应如何写

### 4.2 Comparison with Heuristic Baselines
这一小节建议聚焦在线动态调度场景，对比 Q-learning 与多个 baseline。写作目标是验证：

> 在相同环境、相同资源约束下，Q-learning 超启发式是否能够优于固定单一规则。

建议表格字段：
- Method
- Final Score ↑
- Completed Tasks ↑
- Expired Tasks ↓
- Total Distance ↓
- Charging Events / Queue Burden ↓

写作时可突出两类现象：
1. **固定规则的偏置**：例如最近任务优先有利于降低路径成本，但可能忽略高权重或紧急任务；最早截止时间优先可降低超时，但可能增加总里程；
2. **Q-learning 的优势**：其不固定使用某一种 rule，而是根据任务积压、紧迫性、电量与拥堵状态动态选择规则，因此在综合得分上更有优势。

如果实验结果并不是 Q-learning 在所有指标都最好，也可以按 CVPR 风格正常写：例如说明它在最终总得分上最优，但在单一距离指标上不一定最小，这表明它学到的是“综合权衡”而不是“单指标最优”。

### 4.3 Comparison with Offline MILP Upper Bound
这一小节建议聚焦小规模场景，验证在线策略与离线全局最优之间的差距。根据当前 `god_view_milp_summary.json`，你们已经具备以下可直接写入的结果信息：
- 求解器：Gurobi；
- 求解状态：Optimal；
- 目标值：86.25；
- 总距离：77.70；
- 总迟到量：0.0；
- makespan：42.77；
- 两辆车的语义路径和引擎回放路径。

这一节建议回答两个问题：
1. 在线动态方法与离线最优之间有多大差距？
2. 这个差距主要来自信息不完备、任务在线释放，还是来自充电/时间/载重约束带来的局部次优？

这里很适合写成：
- MILP 给出的是 full-information setting 下的近优参考；
- 在线策略在不知道未来任务的条件下仍能达到较高得分，说明其在动态场景中具有实际意义；
- 当规模提升时，MILP 受求解器 license 和复杂度限制，只能回退到 tiny/small，进一步体现在线方法在实际部署中的必要性。

你们现在 `fallback` 信息也很有价值，可以直接作为论文中的分析点：
- medium 和 small 因 license 限制无法直接求解；
- tiny 可以成功求得最优解；
- 这说明离线精确求解虽然在小规模场景下能提供参考上界，但在更大规模问题中难以直接扩展。

---

## 4. 消融实验建议怎么写

### 4.4 Ablation Study
根据现有代码，我建议至少做以下三组消融：

#### 4.4.1 奖励函数消融
你们当前环境中的 reward 由多项组成：
- score 增量；
- completed tasks 奖励；
- distance 惩罚；
- expired tasks 惩罚；
- emergency unserved 惩罚；
- charge start 惩罚。

因此可以围绕 reward 设计消融实验，例如：
- 去掉距离惩罚；
- 去掉紧急任务惩罚；
- 去掉充电触发惩罚；
- 使用完整 reward。

这类实验很适合回答：
> Q-learning 的性能提升究竟来自哪一类奖励信号？

如果你已经有 `score_ablation_comparison.svg` 这类图，可以把这节作为重点。

#### 4.4.2 动作库消融
由于 Q-learning 的动作实际上是 rule selection，因此还可以比较：
- 仅使用 3 个基础启发式动作；
- 加入 best-score 动作；
- 再加入 nearest-station charging 相关动作；
- 完整 6 动作规则库。

这节回答的问题是：
> 强化学习性能提升到底来自学习能力本身，还是来自更丰富的 rule library？

#### 4.4.3 充电策略消融
当前代码明确区分：
- `optimal_station`
- `nearest_station`

因此可自然形成一组实验：
- 固定调度规则，只改变充电策略；
- 固定 Q-learning，其动作库是否包含 nearest-station rule；
- 比较不同充电决策对 score、distance、expired tasks 的影响。

这节可以突出新能源场景特有的贡献：在传统路径规划问题中，补能逻辑通常不是主角，但在新能源物流中，充电策略会直接改变整体调度质量。

---

## 5. 定性分析建议怎么写

### 4.5 Qualitative Analysis and Visualization
这部分建议结合前端回放和 MILP 语义路径做定性说明。可以写的内容包括：

1. **典型成功案例**：Q-learning 在任务积压高、部分车辆低电量时切换到更适合的 rule，从而避免超时任务爆发；
2. **典型失败案例**：固定规则在高拥堵充电场景下可能出现局部贪心，导致后续任务集中超时；
3. **离线-在线对比案例**：MILP 在已知未来任务时可以提前规划车辆分工，而在线策略只能基于当前可见任务做局部最优决策；
4. **回放一致性分析**：`god_view_milp_summary.json` 中已经包含 semantic route 与 engine replay route，可用来说明离线求解结果与仿真引擎的一致性。

在 CVPR 风格中，这类定性分析通常不是为了“好看”，而是为了帮助读者理解方法行为机制。因此建议不要只放前端截图，而是配合说明：某辆车为何此时充电、为何切换规则、为何产生局部延迟。

---

## 6. 建议最终写成的核心研究问题

为了让 Experiment 部分更像论文而不是项目运行说明，建议开头明确提出本节围绕以下几个研究问题展开：

- **RQ1:** 在动态新能源物流场景中，Q-learning 超启发式是否优于固定启发式调度规则？
- **RQ2:** 在线策略与离线 MILP 全局最优之间的性能差距有多大，其主要来源是什么？
- **RQ3:** 奖励设计、动作库构成与充电策略对强化学习性能的影响分别是什么？
- **RQ4:** 通过可视化回放，能否解释不同方法在典型场景中的行为差异？

有了这几个研究问题之后，Experiment 各小节就会显得非常自然，也更符合 CVPR 风格论文常见的叙述方式。

---

## 7. 建议你后续补充/整理的实验素材

为了把这一节真正写完整，建议你后续优先准备以下内容：

1. **主结果表**
   - 各 heuristic baseline + Q-learning 的 score/completed/expired/distance 对比；

2. **离线 MILP 对比表**
   - online best vs offline MILP（tiny/small）；

3. **训练曲线图**
   - episode vs eval score mean
   - episode vs reward
   - epsilon decay curve（可选）；

4. **消融图**
   - 奖励项消融；
   - 动作库消融；
   - 充电策略消融；

5. **定性图**
   - 前端回放截图；
   - MILP 语义路径与 engine replay 路径示意图；
   - 充电拥堵场景截图。

---

## 8. 可以直接放进论文的过渡句模板

你后面正式写实验时，可以直接参考下面这种 CVPR 风格过渡句：

- “We evaluate the proposed system from four aspects: overall effectiveness, comparison with offline upper bounds, ablation on reward and action design, and qualitative visualization analysis.”
- “Unless otherwise specified, all methods are evaluated under the same dynamic task generation process and vehicle resource constraints.”
- “The offline MILP planner is used as a full-information upper-bound reference on small-scale instances rather than as a deployable online method.”
- “These experiments are designed to answer whether the learned policy selector can outperform fixed heuristics and under what conditions such gains emerge.”

如果你需要，我下一步可以继续把这份中文规划直接扩写成论文里可用的 `Experiment` 中文初稿，或者直接转成 `paper/sec/3_finalcopy.tex` 的英文/LaTeX 结构稿。
