# Data-Structure-HW

> 新能源物流车队协同调度系统  
> 图算法仿真引擎 + 实时后端 + Web 可视化前端

这是一个面向课程项目与演示展示的完整仓库，核心目标是模拟：**有限新能源车队在城市道路网络中，面对动态出现的配送任务时，如何在电量、载重、充电排队、任务时限等约束下完成调度与路径规划。**

---

## 项目亮点

- 图结构建模城市道路网络
- 支持 `Dijkstra`、`A*`、`RRT` 路径规划
- 动态任务按时间释放，模拟真实到达过程
- 车辆具备电量、载重、速度、耗电约束
- 充电站支持排队与负荷建模
- 支持多种调度策略对比
- 提供 Python 引擎 + FastAPI 接口 + Next.js 可视化界面
- 可导出完整实验日志，适合答辩与报告展示

---

## 项目结构

```text
Data-Structure-HW/
├── Engine/                      # Python 仿真引擎与后端
│   ├── Framework/
│   │   ├── api/                 # FastAPI / WebSocket 接口
│   │   ├── configs/             # YAML 配置
│   │   ├── core/                # 图、实体、寻路、仿真主循环
│   │   ├── examples/            # 各类运行脚本
│   │   ├── generator/           # 任务与地图加载/生成
│   │   ├── scheduler/           # 调度策略
│   │   └── output/              # 实验输出结果
│   ├── Map Resource/            # 番禺地图资源与预处理数据
│   ├── docs/                    # 引擎文档
│   └── requirements.txt         # Python 依赖
├── UI/
│   └── logistics-ui/            # Next.js 前端展示界面
├── policy/                      # 扩展策略 / RL / offline 方向
├── 2026-大作业要求.txt
├── 说明.md
├── Readme
├── README_GitHub.md             # GitHub/项目展示版
└── README_答辩版.md              # 学术答辩版
```

---

## 功能概览

### 1. 仿真引擎

- 动态生成并释放任务
- 维护车辆状态、任务状态、站点状态
- 执行调度、移动、充电、回仓等行为
- 输出全过程日志

### 2. 路径规划

当前已支持：
- `Dijkstra`
- `A*`
- `RRT`

适合用于：
- 基线路径最短路对比
- 启发式搜索展示
- 进阶算法实验扩展

### 3. 调度策略

已实现基础策略：
- 最近任务优先
- 最大任务优先

并支持：
- 协同任务扩展
- 多规模实验
- 输出对比结果

### 4. 可视化界面

前端支持：
- 地图展示
- 车辆、任务、充电站状态展示
- 事件日志展示
- 与后端实时联调

---

## 快速开始

## 1) 安装 Engine 依赖

在仓库根目录执行：

```bash
pip install -r Engine/requirements.txt
```

如需仓库扩展依赖：

```bash
pip install -r requirements.txt
```

---

## 2) 运行仿真基线

### 方式 A：在仓库根目录运行

```bash
python -m Engine.Framework.examples.run_panyu_processed_baseline \
  --config "Engine/Framework/configs/panyu_processed_baseline.yaml"
```

### 方式 B：进入 `Engine/` 目录运行

```bash
cd Engine
python -m Framework.examples.run_panyu_processed_baseline \
  --config "Framework/configs/panyu_processed_baseline.yaml"
```

运行后结果通常输出到：

```text
Engine/Framework/output/
```

---

## 3) 启动后端接口

```bash
cd Engine
python -m uvicorn Framework.api.server:app --host 127.0.0.1 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

---

## 4) 启动前端界面

```bash
cd UI/logistics-ui
npm install
npm run dev
```

访问：

```text
http://localhost:3000
```

---

## 前后端联调说明

如果需要让前端连接 Python 引擎后端，请在 `UI/logistics-ui/` 下创建 `.env.local`：

```bash
NEXT_PUBLIC_USE_ENGINE_BACKEND=1
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_AMAP_KEY=你的高德 Web JS API Key
NEXT_PUBLIC_AMAP_SECURITY_CODE=你的高德安全密钥
```

说明：
- `NEXT_PUBLIC_API_URL` 指向后端地址
- 若不配置高德地图 Key，前端通常会回退到 Canvas 地图视图
- 本地联调推荐固定使用 `127.0.0.1:8000`

推荐联调顺序：
1. 先启动 `Engine` 后端
2. 再启动 `UI` 前端
3. 打开页面观察车辆、任务和事件日志是否持续刷新

---

## 常用运行命令

### 运行随机基线

```bash
cd Engine
python -m Framework.examples.run_baseline \
  --config "Framework/configs/random_baseline.yaml"
```

### 运行番禺 processed 基线

```bash
cd Engine
python -m Framework.examples.run_panyu_processed_baseline \
  --config "Framework/configs/panyu_processed_baseline.yaml"
```

### 运行实验矩阵

```bash
cd Engine
python -m Framework.examples.run_experiment_matrix \
  --config "Framework/configs/experiment_matrix.yaml"
```

---

## 功能截图位

> 下面的位置可以在你后续整理仓库时替换成真实截图。

### 主界面总览

```text
[截图位 1：系统主界面 / 地图总览]
建议展示：地图、车辆、任务面板、统计面板同时出现的界面
```

### 仿真运行中

```text
[截图位 2：仿真过程中的车辆移动与任务变化]
建议展示：任务动态出现、车辆状态变化、事件日志刷新
```

### 充电站排队/负荷展示

```text
[截图位 3：车辆进站充电 / 队列状态]
建议展示：排队、占桩、低电量补能相关画面
```

### 策略对比或实验结果

```text
[截图位 4：不同策略结果对比 / 输出摘要]
建议展示：summary 表、统计图或 UI compare 页面
```

如果你之后要补图，推荐在仓库中新建：

```text
assets/screenshots/
```

例如：
- `assets/screenshots/ui-overview.png`
- `assets/screenshots/runtime-demo.png`
- `assets/screenshots/charging-station.png`
- `assets/screenshots/strategy-compare.png`

---

## 输出结果说明

引擎可导出：
- `step_log`
- `vehicle_log`
- `task_log`
- `station_log`
- `events`

这些结果可用于：
- 报告实验分析
- 不同调度策略对比
- 前后端联调验证
- 答辩展示材料整理

---

## 推荐阅读

- `Engine/README.md`
- `Engine/Framework/README.md`
- `Engine/docs/01-快速开始与常用命令.md`
- `Engine/docs/02-协作接口说明.md`
- `说明.md`

---

## 适合展示的卖点

如果你准备把这个仓库作为 GitHub 展示项目，建议突出这几点：

- **不是单纯算法题，而是完整系统工程**
- **同时包含仿真引擎、后端接口、前端可视化**
- **支持真实地图数据与动态任务场景**
- **结果可导出、可复现、可对比**

---

## License

仓库根目录已包含 `LICENSE` 文件，如需公开展示，可在此补充更具体的使用说明。
