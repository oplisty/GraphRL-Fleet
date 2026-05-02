# 4.1 Experimental Setup

本节从实验环境、对比方法、评价指标与实现细节四个方面介绍实验设置。整体上，我们希望在统一的动态新能源物流调度环境中，系统性评估启发式基线、Q-learning 超启发式以及离线 MILP 方法在任务完成质量、运行代价与扩展性方面的差异。

## 4.1.1 环境与场景设置

环境以图结构路网为基础，显式建模有限数量车辆、动态释放任务、车辆电量与载重约束、充电站资源以及任务截止时间。根据 `Engine/Framework/core/config.py` 中的预设场景，实验支持 `small`、`medium` 与 `large` 三种不同规模，其配置如下：
- **small**：包含 5 辆车、30 个动态任务、2 个充电站和 25 个道路节点，地图尺寸为 \(30\times 30\)，仿真时域长度为 180；该规模主要用于快速验证算法有效性与训练收敛行为。
- **medium**：包含 10 辆车、100 个动态任务、4 个充电站和 60 个道路节点，地图尺寸为 \(50\times 50\)，仿真时域长度为 300；该规模用于测试方法在更高任务密度与更复杂补能压力下的稳定性。
- **large**：包含 20 辆车、300 个动态任务、8 个充电站和 120 个道路节点，地图尺寸为 \(80\times 80\)，仿真时域长度为 480，且每个充电站默认配置 3 个充电桩；该规模主要用于考察方法在复杂动态场景中的扩展能力与鲁棒性。

除规模因素外，由于充电决策会显著影响车辆可用性、任务延迟与整体得分，实验还设置了 `optimal_station` 与 `nearest_station` 两类充电策略。前者在选站时综合考虑距离与站点负载，后者则优先选择最近充电站。

## 4.1.3 评价指标

为了全面评价不同方法在动态新能源物流场景中的表现，我们从任务效能与运行成本两个维度报告实验指标。具体而言，各指标的定义如下：

**任务效能指标：**
- **Final Score**：For each task \(\tau_i\), its reward is defined as
\[
\mathrm{Score}(\tau_i)=R_0-\lambda_d\,\mathrm{dist}_i-\lambda_w\,\mathrm{wait}_i-\mathbb{I}(\mathrm{overdue}_i>0)\cdot P_{\mathrm{overdue}},
\]
where \(R_0\) corresponds to \texttt{reward\_base}, \(\lambda_d\) corresponds to \texttt{distance\_penalty}, \(\lambda_w\) corresponds to \texttt{wait\_time\_penalty}, and \(P_{\mathrm{overdue}}\) corresponds to \texttt{overdue\_penalty}. Here, \(\mathrm{dist}_i\) denotes the total travel distance for serving task \(i\), \(\mathrm{wait}_i = t_i^{\mathrm{finish}} - r_i\) denotes the elapsed time from task release to task completion, and \(\mathrm{overdue}_i = t_i^{\mathrm{finish}} - d_i\) denotes the amount of deadline violation.

- **Completed Tasks**：仿真结束时已完成任务的数量，用于衡量调度策略的任务服务能力。
- **Expired Tasks**：仿真结束时已过截止时间且未完成任务的数量，用于刻画任务失败程度。
- **Total Tardiness**：用于离线 MILP 结果分析，其计算形式为所有任务迟到量之和，即 \(\sum_n \max(0, \mathrm{arr}_n-d_n)\)。当任务在截止时间之前完成时，其迟到量记为 0。

**运行成本指标：**
- **Total Distance**：所有车辆累计行驶距离之和。
- **Steps / Makespan**：用于刻画调度过程的时间跨度。在在线仿真中，`Steps` 表示从初始时刻到仿真终止时所经历的离散时间步数；在离线 MILP 中，`Makespan` 表示所有车辆完成服务并回仓后的最大结束时间，即整体完工时间。
- **Charging Burden**：用于反映新能源场景中的补能成本。我们采用两种统计方式：1）**充电触发次数**和**平均排队负载**，前者反映系统进入补能过程的频繁程度，后者反映充电资源竞争带来的拥堵压力。

**训练阶段指标：**
- **Total Reward**：在单个训练 episode 中所有时间步即时奖励之和，即 \(\sum_t r_t\)，用于衡量当前策略在训练环境中的总体收益。
- **Eval Score Mean**：每轮训练后使用 greedy policy 在若干评估回合上得到的最终得分均值，用于衡量学习策略的稳定性能，而不是仅依赖单次训练轨迹。



