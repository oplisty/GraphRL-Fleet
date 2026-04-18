## 2.数据层
The data resource layer provides a unified representation of the environment for the whole system and serves as the foundation for subsequent path planning, task scheduling, and state simulation. To satisfy the course requirement of using a graph structure for road representation and routing, this paper first models the urban delivery scenario as a weighted directed graph
\[
G=(V,E,W),
\]
where the node set \(V\) represents road intersections, depots, candidate task locations, and charging stations; the edge set \(E\subseteq V\times V\) represents road connectivity; and the weight function \(W:E\rightarrow \mathbb{R}^{+}\) describes the distance or travel cost of each edge. Based on this representation, the entire logistics environment can be mapped into a discrete graph space, which provides a computable foundation for shortest-path search, reachability analysis, and energy consumption evaluation.

In the implementation, the system denotes the depot as node \(v_d\in V\), the set of charging stations as
\[
S=\{s_1,s_2,\dots,s_m\}\subseteq V,
\]
and generates dynamic tasks from the candidate task node set \(V_T\subseteq V\). For any task \(\tau_i\), it can be represented as the following four-tuple:
\[
\tau_i=(r_i,\, v_i,\, w_i,\, d_i),
\]
where \(r_i\) is the release time of the task, \(v_i\in V_T\) is the task location, \(w_i\) is the cargo weight, and \(d_i\) is the deadline. This representation allows each task to include not only spatial information but also explicit time constraints, thereby supporting online scheduling decisions in dynamic arrival scenarios.

Furthermore, the data resource layer maintains the static parameter sets of vehicles and stations. For example, for vehicle \(k\), its state parameters can be defined as
\[
\mathbf{x}_k=(b_k^{\max},\, b_k,\, c_k,\, v_k^{\text{cur}},\, \eta_k),
\]
where \(b_k^{\max}\) and \(b_k\) denote the maximum battery level and current battery level, respectively; \(c_k\) is the load capacity limit; \(v_k^{\text{cur}}\) is the current node location; and \(\eta_k\) is the energy consumption per unit distance. For charging station \(s_j\), the system records attributes such as the number of chargers, queue length, and charging rate. In this way, the data resource layer provides not only the static topology of the road network but also a unified description of the parameters of tasks, vehicles, and charging facilities.

## 3. 算法层

在数据资源层完成环境形式化之后，算法层进一步负责在图结构路网 \(G=(V,E,W)\) 上生成可执行的路径与调度决策。本文将该层划分为两个个相互耦合的基础模块：路径规划module与任务调度 模块。

### 3.1 路径规划模块

For any vehicle \(k\) and target node \(v\in V\), the goal of the path planning module is to find a feasible path \(P_k(v_k^{\text{cur}}, v)\) on graph \(G\) from the current location \(v_k^{\text{cur}}\) to the target node \(v\). Let the total cost of a path \(P\) be
\[
C(P)=\sum_{e\in P} W(e),
\]
then the shortest path problem can be written as
\[
P_k^*(v_k^{\text{cur}}, v)=\arg\min_{P\in \mathcal{P}(v_k^{\text{cur}}, v)} C(P),
\]
where \(\mathcal{P}(v_k^{\text{cur}}, v)\) denotes the set of all feasible paths from \(v_k^{\text{cur}}\) to \(v\).

Based on this unified objective, the system implements three path planning baselines.

\textbf{Dijkstra:} A classic shortest-path algorithm for weighted graphs. It directly minimizes the total path cost \(C(P)\) and can stably return the global optimal path. Therefore, it is used as the standard shortest-path baseline in the system.

\textbf{A*:} This method introduces a heuristic evaluation function \(h(u,v)\) on top of Dijkstra and uses
\[
f(n)=g(n)+h(n)
\]
as the search priority, where \(g(n)\) is the known accumulated cost from the start node to the current node \(n\), and \(h(n)\) is the heuristic estimated cost from \(n\) to the target node. This method maintains good search quality while reducing unnecessary node expansions, thereby improving the efficiency of each query.

\textbf{RRT:} A sampling-based search method. It does not directly guarantee a strict shortest path in the graph sense, but explores a large state space through random tree expansion. This provides an interface for future research under more complex path planning settings.

In the new energy delivery scenario, path planning is not only used for travel from the current node to a task node, but also needs to support feasibility checking for returning to the depot after task completion and visiting a charging station when the battery is low. Therefore, for a task \(\tau_i=(r_i, v_i, w_i, d_i)\), the system not only computes \(C(P_k^*(v_k^{\text{cur}}, v_i))\), but also further evaluates whether the vehicle satisfies the basic energy consumption constraint. Let \(\eta_k\) denote the energy consumption per unit distance of vehicle \(k\). Then the energy consumption along path \(P\) can be approximately written as
\[
E_k(P)=\eta_k\, C(P).
\]
Only when the current battery level \(b_k\) is sufficient to support the planned trip is the path regarded as executable.

### 3.2 调度策略 baselines

在获得可行路径之后，调度模块进一步决定应将哪个任务分配给哪一辆车。对于当前可见任务集合 \(\mathcal{T}_t\) 与车辆 \(k\) 的当前状态 \(\mathbf{x}_k\)，baseline 调度策略本质上是在所有候选任务中定义一个优先级评分函数 \(\phi_k(\tau_i)\)，并选择
\[
\tau_k^*=\arg\max_{\tau_i\in \mathcal{T}_t} \phi_k(\tau_i)
\]
作为当前时刻最优先分配的任务。不同 baseline 的差异体现在评分函数 \(\phi_k(\tau_i)\) 的定义方式上。
\begin{itemize}
* 最近任务优先策略:最小路径成本为核心准则，其policy可表示为
\[
\tau_k^*=\arg\min_{\tau_i\in \mathcal{T}_t} C\bigl(P_k^*(v_k^{\text{cur}}, v_i)\bigr).
\]


最大重量优先策略:关注高负载任务的优先处理。对于任务 \(\tau_i=(r_i,v_i,w_i,d_i)\)，其policy可写为
\[
\tau_k^*=\arg\max_{\tau_i\in \mathcal{T}_t,\, w_i\le c_k} w_i,
\]


最早截止时间:以任务时效性为核心，其策略可表述为
\[
\tau_k^*=\arg\min_{\tau_i\in \mathcal{T}_t} d_i.
\]

在上述 baseline 之外，我们进一步实现了基于 Q-learning 的在线强化学习策略选择模块，以及上帝视角下的离线 MILP 全局优化模块。二者分别对应“基于交互学习的在线决策”与“基于精确优化的离线求解”两类不同的方法范式。

* Q-learning 模块遵循标准强化学习建模：在每个时间步 \(t\)，环境根据当前仿真状态产生离散状态 \(s_t\)，agent 选择动作 \(a_t\)，并从环境获得即时奖励 \(r_t\) 与下一状态 \(s_{t+1}\)。在本项目中，状态 \(s_t\) 由车辆利用率、待处理任务压力、电量水平以及任务完成情况等统计量离散编码得到；动作 \(a_t\) 并不直接表示具体路径，而是表示对某一底层调度规则的选择，例如最近任务优先、最大重量优先或最早截止时间优先。这样一来，Q-learning 的作用可以理解为在不同环境状态下自适应选择更优的 baseline 策略。

记状态--动作价值函数为 \(Q(s,a)\)，则其迭代更新遵循 Bellman 最优方程对应的时序差分形式
\[
Q(s_t,a_t) \leftarrow Q(s_t,a_t) + \alpha \Bigl[r_t + \gamma \max_{a'} Q(s_{t+1},a') - Q(s_t,a_t)\Bigr],
\]
其中 \(\alpha\) 为学习率，\(\gamma\) 为折扣因子。训练阶段采用 \(\epsilon\)-greedy 机制在探索与利用之间取得平衡，即以概率 \(\epsilon\) 选择随机动作，以概率 \(1-\epsilon\) 选择 \(\arg\max_a Q(s_t,a)\)，并在训练过程中逐步衰减 \(\epsilon\)。由于环境 reward 已综合反映任务完成数、过期任务数以及最终得分变化，因此该更新过程本质上是在最大化长期累计回报
\[
G_t = \sum_{\ell=0}^{\infty} \gamma^{\ell} r_{t+\ell+1}.
\]
相较于直接端到端学习连续调度动作，该设计保留了启发式规则的可解释性，同时利用强化学习提升了策略切换的自适应能力。

**Algorithm 1: Q-learning-based policy selection**

```text
Input: training episodes M, learning rate α, discount factor γ,
       initial exploration rate ε, decay factor ρ,
       discrete state space S, action space A
Output: learned Q-table Q

Initialize Q(s,a) = 0, for all (s,a) ∈ S × A
for episode = 1 to M do
    Reset environment and obtain initial state s0
    while episode not terminated do
        With probability ε choose a random action at
        Otherwise choose at = argmax_a Q(st, a)
        Execute action at in environment
        Observe reward rt, next state st+1, and termination flag
        Update Q-table:
            Q(st,at) ← Q(st,at) + α [rt + γ max_a' Q(st+1,a') - Q(st,at)]
        st ← st+1
    end while
    ε ← max(εmin, ρ · ε)
end for
Return Q
```

### 3.4 Offline MILP optimization

与在线学习方法不同，离线 MILP 模块假设任务集合在规划开始时已全部已知，即所有 \(\tau_i=(r_i,v_i,w_i,d_i)\) 可以在优化前一次性获得。在这一前提下，系统将仓库、任务节点与充电站副本统一扩展为节点集合，并定义二元变量 \(x_{vij}\in\{0,1\}\) 表示车辆 \(v\) 是否经过弧 \((i,j)\)。进一步地，模型还联合维护到达时刻、载重、电量、充电量与迟到量等变量，从而将路径规划、任务分配与补能决策统一纳入同一个优化框架。

其目标函数可概括写为
\[
\min \sum_{v}\sum_{(i,j)} C_{ij} x_{vij} + \lambda_1 \sum_{v}\sum_{n\in \mathcal{T}} \mathrm{tardy}_{vn} + \lambda_2 T_{\max},
\]
其中 \(C_{ij}\) 表示弧代价，\(\mathrm{tardy}_{vn}\) 表示任务超时量，\(T_{\max}\) 表示全局完工时间。约束方面，模型同时满足：1）每个任务恰好被访问一次；2）每辆车从仓库出发并最终回仓；3）流守恒约束保证路径连续性；4）载重变量随任务完成而递减；5）SOC 变量随行驶能耗与充电行为动态演化；6）到达时刻必须满足释放时间、服务时间与截止时间要求。由于代码实现中还引入了速度离散层和分段线性充电近似，因此该 MILP 不仅能描述任务分配关系，还能在一定程度上刻画新能源车辆的真实运行约束。

**Algorithm 2: Offline MILP-based global planning**

```text
Input: full task set T, vehicle set V, expanded node set N,
       arc cost matrix C, battery and capacity constraints
Output: offline global assignment and route plan

Construct expanded graph with depot, task nodes, and station copies
Define binary routing variables x(v,i,j)
Define auxiliary variables for arrival time, load, SOC,
charge amount, charge time, and tardiness
Build objective:
    minimize total routing cost + tardiness penalty + makespan penalty
Add constraints:
    each task is visited exactly once
    each used vehicle starts from depot and returns to depot
    flow conservation holds on every visited node
    load evolution satisfies demand and capacity limits
    SOC evolution satisfies energy consumption and charging constraints
    arrival times satisfy release time, service time, and deadline constraints
Call MILP solver (e.g., Gurobi/CPLEX) to obtain optimal solution
Decode semantic routes and task-to-vehicle assignments
Replay the offline plan in the simulation engine for comparison
Return offline plan
```

## 4. 仿真引擎层

仿真引擎层负责将数据资源层定义的静态环境与算法层输出的调度动作转化为可执行的时序过程，是整个系统进行动态闭环模拟的核心。与仅关注单次路径查询或局部派单不同，该层显式建模了任务释放、车辆运动、电量消耗、充电排队与任务完成等随时间演化的状态变量，从而使新能源物流调度问题能够在统一的时间轴上被持续求解与评估。

在实现上，系统采用离散时间推进机制。记时刻 \(t\) 的全局环境状态为 \(\mathcal{S}_t\)，算法层生成的联合动作记为 \(\mathcal{A}_t\)，则仿真引擎可被形式化为一个状态转移过程
\[
\mathcal{S}_{t+1} = \Phi(\mathcal{S}_t, \mathcal{A}_t),
\]
其中 \(\Phi(\cdot)\) 表示由任务更新、车辆推进、能耗结算、充电调度和统计记录共同构成的环境演化算子。具体而言，在每一个时间步中，系统首先根据释放时间将新任务并入待调度集合，并剔除已超过截止时间的失效任务；随后根据当前车辆状态与候选任务集调用调度器生成派单动作；接着执行路径推进与任务服务，同时更新车辆位置、剩余电量、载重状态与任务完成情况；最后处理充电站的排队、占桩和补能事件，并同步刷新系统级统计量。

该层的关键作用在于将路径规划与任务调度从“静态选择问题”扩展为“受资源约束的动态演化问题”。例如，当车辆 \(k\) 沿路径 \(P\) 行驶时，其电量会按照前文定义的能耗模型 \(E_k(P)=\eta_k C(P)\) 持续递减；当 \(b_k\) 无法支撑车辆完成既定行程时，仿真引擎会触发充电站选择与排队逻辑，并在站点容量受限的条件下更新等待状态。类似地，对于动态释放任务，仿真引擎不仅决定任务何时进入可分配集合，也决定其是否因超时而转化为惩罚项。由此，任务收益、车辆利用率、路径长度与充电负载等指标都可以在统一仿真框架下被一致计算。

## 5. Frontend and Backend

前端层和后端层并不直接参与路径规划或调度优化本身，而是负责将仿真引擎内部的状态、事件与统计结果组织为可访问、可回放、可分析的外部表示，从而使整个系统具备完整的实验闭环与交互能力。

在实现上，后端部分承担统一的状态封装与服务暴露功能。系统通过 FastAPI 与 WebSocket 建立持续通信通道，将时刻 \(t\) 的环境状态 \(\mathcal{S}_t\) 投影为前端可消费的数据对象，例如车辆位置、任务状态、充电站负载、累计得分与事件日志等；与此同时，后端还负责接收来自外部的控制指令，并将其转换为对仿真进程或算法模块的调用请求。除常规的开始、暂停、恢复与停止控制外，该层还统一封装了 Q-learning 训练/推理接口、离线 MILP 求解接口以及结果导出接口，使实验过程能够在同一服务框架下被调度与复用。换言之，该层实质上提供了一个映射
\[
\Psi: \mathcal{S}_t \mapsto \mathcal{O}_t,
\]
其中 \(\mathcal{O}_t\) 表示面向外部接口的结构化观测结果，从而将底层复杂状态转换为标准化服务输出。

在此基础上，前端可视化模块进一步将 \(\mathcal{O}_t\) 转化为用户可理解的图形表达。具体而言，界面持续呈现道路网络、仓库、任务节点、充电站与车辆的空间分布，并同步更新任务完成情况、车辆利用率、路径代价、充电队列长度与系统得分等关键指标。更重要的是，该层并非仅承担静态展示功能，而是为策略切换、离线回放、训练触发和结果对比提供统一交互入口。由此，原本分散在仿真日志、调度输出与统计结果中的多源信息，被重新整合为面向分析与展示的可视化工作流。

## 6. 各层之间的递进关系与协同机制

综合上述分析，可以将整个系统的工作流程理解为一个自底向上的递进结构。首先，数据资源层提供道路网络、任务候选点、充电站与仓库等基础环境信息；随后，算法层在这些环境信息之上完成路径搜索与调度决策；接着，仿真引擎层根据算法输出推动系统状态在时间轴上演化，并处理任务释放、电量消耗、充电排队和收益统计等动态过程；最后，系统接口与可视化层将这些动态状态与算法能力统一封装并对外展示，从而形成从环境建模、算法求解到仿真执行与结果交互的完整闭环。

这种层层递进的结构保证了系统既具备较强的模块独立性，又能够形成清晰的数据流和控制流：底层为上层提供资源与状态，上层对下层进行调度、封装与展示反馈，最终形成一个从环境建模、算法决策到仿真执行和可视化输出的完整系统闭环。也正是在这种框架之下，本文实现了课程要求中的主要功能，并为后续在更大规模场景、更复杂调度策略以及更强学习方法上的扩展奠定了基础。
