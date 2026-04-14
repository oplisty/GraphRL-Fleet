# 系统检查清单

基于当前仓库代码对 `Engine` 调度与仿真功能进行核查，结论如下。

## 1. 策略完善情况

### 1.1 最近任务优先
- [x] 已实现
- 说明：`NearestTaskScheduler` 会为每辆空闲车选择当前可执行、且最短路距离最近的待处理任务。
- 对应代码：
  - `Engine/Framework/scheduler/nearest_task.py`
- 备注：这里的“最近”基于 `PathFinder.shortest_distance(...)`，不是简单欧氏距离。

### 1.2 最大重量优先
- [x] 已实现
- 说明：`HeaviestTaskScheduler` 按任务重量从大到小排序，再为任务匹配最近且可执行的空闲车辆。
- 对应代码：
  - `Engine/Framework/scheduler/heaviest_task.py`

### 1.3 最早截止优先
- [ ] 未独立实现
- 说明：系统前端/接口层虽然出现了 `earliest_deadline` 这个策略名，但后端并没有专门的 EDF 调度器类。
- 当前实际行为：
  - `Engine/Framework/api/server.py` 中 `_map_strategy(...)` 把 `earliest_deadline` 映射到了 `nearest`
- 结论：目前**不是最早截止优先真实策略**，而是复用了最近任务优先。

### 1.4 最近充电站
- [x] 已实现
- 说明：当车辆需要充电时，系统会在“可达”的充电站中进行选择；若不考虑队列与负载权重，本质支持最近站选择。
- 相关核心逻辑：
  - `Environment._redirect_to_charge(...)`
  - `Environment._choose_reachable_station(...)`
- 对应代码：
  - `Engine/Framework/core/simulation.py`
- 备注：当前不是单独暴露成一个“调度策略按钮”，而是内置在车辆低电量处理逻辑中。

### 1.5 最优充电站
- [x] 已实现（规则型）
- 说明：当前采用固定规则，不训练模型。系统按以下代价选择充电站：
  - 路径距离
  - 排队长度
  - 已占用充电桩数
- 代价函数：
  - `total_cost = distance + charge_queue_weight * queue_length + charge_occupied_weight * occupied_piles`
- 对应代码：
  - `Engine/Framework/core/simulation.py`
  - `Engine/Framework/core/config.py`
- 结论：这属于你说的“先不训练，只固定用规则跑”的**最优充电站规则版**。

---

## 2. 系统功能完整性检查

### 2.1 任务动态出现
- [x] 已实现
- 说明：任务生成时带有 `release_time`，仿真过程中按时间逐步释放，不是一开始全部出现。
- 对应代码：
  - 任务生成：
    - `Engine/Framework/generator/task_generator.py`
    - `Engine/Framework/generator/real_task_generator.py`
  - 运行时释放：
    - `Engine/Framework/core/simulation.py` 中 `_release_tasks()`

### 2.2 车辆能执行任务
- [x] 已实现
- 说明：车辆可被分配到任务点，沿路网移动，到达后完成配送，并按配置自动回仓。
- 对应代码：
  - 调度分配：`dispatch(...)`、`_dispatch_vehicle_to_task(...)`
  - 移动执行：`_update_vehicles()`、`_advance_vehicle()`
  - 完成任务：`_on_reach_task()`、`_finalize_task_completion()`
  - 文件：`Engine/Framework/core/simulation.py`

### 2.3 低电量会触发充电
- [x] 已实现
- 说明：车辆空闲时若电量低于阈值，或当前电量不足以安全回仓，会自动转向充电站。
- 对应代码：
  - `Engine/Framework/core/simulation.py`
    - `_should_charge()`
    - `_redirect_to_charge()`
- 相关配置：
  - `Engine/Framework/core/config.py`
    - `low_battery_ratio`
    - `charge_to_ratio`
    - `safety_energy_margin`

### 2.4 充电站有队列
- [x] 已实现
- 说明：充电站维护等待队列和充电桩占用情况，车到站后可排队，空闲桩会从队列中取车开始充电。
- 对应代码：
  - 数据结构：`Engine/Framework/core/entities.py`
    - `ChargingStation.queue`
    - `ChargingStation.charging_slots`
  - 仿真更新：`Engine/Framework/core/simulation.py`
    - `_on_reach_station()`
    - `_update_stations()`

### 2.5 能统计分数
- [x] 已实现
- 说明：系统维护总分 `total_score`，任务完成按距离、等待时间、是否超时计算得分；任务过期会扣分；UI 也能读取统计结果。
- 对应代码：
  - 分数计算：
    - `Engine/Framework/core/simulation.py`
      - `_compute_task_score()`
      - `_finalize_task_completion()`
      - `_expire_task()`
  - 统计汇总：
    - `Engine/Framework/api/server.py` 中 `_build_statistics()`

---

## 3. 总结结论

### 已完善/可直接用于规则实验的部分
- [x] 最近任务优先
- [x] 最大重量优先
- [x] 最近充电站（内置逻辑）
- [x] 最优充电站（固定规则版）
- [x] 任务动态出现
- [x] 车辆执行任务
- [x] 低电量自动充电
- [x] 充电站排队
- [x] 分数统计

### 尚未完善的部分
- [ ] 最早截止优先（EDF）
  - 目前只是接口名存在，实际映射到 `nearest`，需要单独新增一个 scheduler 才算真正完成。

---

## 4. 建议下一步

如果你要把策略列表补完整，优先建议新增：

- [ ] `EarliestDeadlineScheduler`
  - 按 `deadline` 最小优先，车辆侧继续保留容量/电量/可回仓可行性检查

如果你要让“最近充电站 / 最优充电站”更清晰可演示，建议继续拆成可切换配置：

- [ ] 纯最近站模式：只按最短路距离选站
- [ ] 规则最优站模式：按 距离 + 排队 + 占用 选站

这样更便于在报告里做策略对比。
