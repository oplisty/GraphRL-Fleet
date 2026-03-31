# 🔋 新能源物流车队协同调度系统

数据结构课程大作业 - 新能源物流车队协同调度模拟系统

## 📋 项目简介

本项目是一个基于图算法的新能源物流车队协同调度模拟系统，使用 Next.js + TypeScript 构建。系统模拟了城市中新能源配送车队的动态调度过程，包括路径规划、任务分配、车辆管理、充电站调度等功能。

## ✨ 功能特点

### 核心功能

- **图结构道路网络**：使用邻接表实现道路网络，支持随机生成和自定义网络
- **寻路算法**：实现 Dijkstra 和 A* 两种经典寻路算法
- **动态任务调度**：模拟随机出现的配送任务，包含时间、位置、重量等属性
- **车辆管理**：管理车队中的车辆，包括电量、载重、状态等
- **充电站调度**：考虑充电站的排队与负荷压力
- **多种调度策略**：支持6种调度策略

### 调度策略

1. **最近任务优先** (Nearest First)
2. **最大任务优先** (Largest First) - 按货物重量
3. **最高收益优先** (Highest Reward)
4. **最早截止优先** (Earliest Deadline)
5. **均衡策略** (Balanced) - 综合多因素
6. **协同调度** (Collaborative) - 多车协作

### 问题规模

支持4种不同规模的问题模拟：

| 规模 | 车辆数 | 节点数 | 充电站数 | 任务生成率 |
|------|--------|--------|----------|------------|
| 小规模 | 5 | 15 | 2 | 0.5/分钟 |
| 中等规模 | 10 | 30 | 4 | 1/分钟 |
| 大规模 | 20 | 50 | 6 | 2/分钟 |
| 超大规模 | 30 | 80 | 10 | 3/分钟 |

## 🖥️ 技术栈

- **框架**: Next.js 16 (App Router)
- **语言**: TypeScript
- **样式**: Tailwind CSS
- **可视化**: HTML5 Canvas
- **状态管理**: React Hooks

## 📁 项目结构

```
logistics-ui/
├── app/
│   ├── components/          # UI组件
│   │   ├── MapCanvas.tsx         # 地图可视化画布
│   │   ├── VehiclePanel.tsx      # 车辆状态面板
│   │   ├── TaskPanel.tsx         # 任务列表面板
│   │   ├── ChargingStationPanel.tsx  # 充电站面板
│   │   ├── ControlPanel.tsx      # 控制面板
│   │   ├── StatisticsPanel.tsx   # 统计数据面板
│   │   └── EventLog.tsx          # 事件日志组件
│   ├── core/                # 核心逻辑
│   │   ├── graph.ts              # 图算法实现
│   │   └── simulation.ts         # 模拟引擎
│   ├── types/               # TypeScript类型定义
│   │   └── index.ts
│   ├── compare/             # 策略对比页面
│   │   └── page.tsx
│   ├── globals.css          # 全局样式
│   ├── layout.tsx           # 布局组件
│   └── page.tsx             # 主页面
├── public/                  # 静态资源
├── package.json
└── README.md
```

## 🚀 快速开始（从 git clone 到可复现）

本节用于指导组员从零开始复现，默认系统为 macOS/Linux。

### 1. 克隆仓库

```bash
git clone <你的仓库地址>
cd Data-Structure-HW
```

### 2. 准备 Engine Python 环境

建议使用 Conda，并确保在 Engine 目录安装依赖。

```bash
conda create -n DSHW python=3.10 -y
conda activate DSHW
cd Engine
pip install -r requirements.txt
```

说明：

- 若使用真实番禺 processed 地图，常见还需要 parquet 依赖（pyarrow 或 fastparquet）。
- 若本机缺包，可执行：

```bash
conda install -n DSHW -y -c conda-forge fastapi uvicorn websockets pyproj shapely fastparquet
```

### 3. 准备 UI 依赖

打开第二个终端：

```bash
cd Data-Structure-HW/UI/logistics-ui
npm install
```

### 4. 配置 UI 环境变量（关键）

在 UI 目录创建 .env.local 文件（该文件默认不会被 git 提交）：

```bash
NEXT_PUBLIC_USE_ENGINE_BACKEND=1
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_AMAP_KEY=你的高德Web端JSAPI Key
# 可选（高德控制台开启安全密钥时需要）
NEXT_PUBLIC_AMAP_SECURITY_CODE=你的高德安全密钥

# 可选：地图显示范围
NEXT_PUBLIC_MAP_CENTER_LNG=113.3845
NEXT_PUBLIC_MAP_CENTER_LAT=22.9377
NEXT_PUBLIC_MAP_SPAN_DEGREE=0.08
```

说明：

- NEXT_PUBLIC_AMAP_KEY 不配置时，页面会回退到 Canvas 视图。
- 若配置了 AMap Key，页面会使用高德底图叠加仿真图层。

### 5. 启动 Engine 服务（终端 1）

在 Engine 目录执行：

```bash
cd Data-Structure-HW/Engine
conda run -n DSHW python -m Framework.api.server
```

看到以下日志说明后端启动成功：

- Application startup complete
- Uvicorn running on http://0.0.0.0:8000

### 6. 启动 UI 服务（终端 2）

在 UI 目录执行：

```bash
cd Data-Structure-HW/UI/logistics-ui
npm run dev
```

浏览器访问：

- http://localhost:3000

### 7. 联调验证清单（确认真的复现成功）

在页面按以下步骤检查：

1. 点击“开始”，仿真时间开始增长。
2. 车辆状态、任务状态、统计数据持续刷新。
3. 地图模式：
	- 配置了 AMap Key：显示高德底图。
	- 未配置 AMap Key：显示 Canvas 地图。
4. 若使用远端 Engine，浏览器控制台不应出现持续 WebSocket 连接失败。

### 8. 多人协作复现注意事项（最容易踩坑）

1. .env.local 不会被 git 提交：每个同学都要自己创建。
2. AMap Key 可能有域名/IP 白名单：同学机器若不在白名单会无法加载地图。
3. 后端地址必须可达：
	- 本机访问：NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
	- 局域网访问：NEXT_PUBLIC_API_URL=http://你的局域网IP:8000
4. 若同一台机器端口被占用，需先释放 3000 或 8000 端口。

### 9. 常见问题排查

#### Q1：点击“开始”没反应

- 检查 Engine 是否启动成功并监听 8000。
- 检查 .env.local 中 NEXT_PUBLIC_API_URL 是否正确。
- 检查浏览器控制台是否有 WebSocket 错误。

#### Q2：朋友 git 下来运行不了

- 通常是没有本地 .env.local 或 AMap Key 白名单未放行。
- 让对方按本 README 第 4 步重新配置。

#### Q3：后端启动即退出

- 多数是 Python 环境或依赖不完整。
- 重新确认 Conda 环境和 Engine/requirements.txt 安装是否成功。

#### Q4：地图不显示，只看到空白区域

- 优先检查 NEXT_PUBLIC_AMAP_KEY 与 NEXT_PUBLIC_AMAP_SECURITY_CODE。
- 暂时移除 AMap Key 可回退到 Canvas 模式，确认主流程先跑通。

### 构建生产版本

```bash
npm run build
npm start
```

## 📖 使用说明

### 主界面

1. **控制面板**（左上）：控制模拟的启动/暂停/停止/重置，调整速度和策略
2. **统计面板**（左下）：查看实时统计数据和事件日志
3. **地图画布**（中间）：可视化道路网络、车辆、任务和充电站
4. **右侧面板**：切换查看车队、任务、充电站详情

### 地图操作

- **拖拽**：按住鼠标左键拖动地图
- **缩放**：使用鼠标滚轮或右下角按钮缩放
- **重置**：点击重置按钮恢复默认视图
- **点击**：点击节点查看详情

### 策略对比

访问 `/compare` 页面进行不同调度策略的对比测试。

## 🎯 评分要点

### 完成分（功能全面性）

- ✅ 车辆数目有限，具有电量和载重上限
- ✅ 动态生成任务（时间、地点、重量随机）
- ✅ 任务评分系统（时间越早路径越短得分越高）
- ✅ 超时扣分机制
- ✅ 自动寻找最近充电站补能
- ✅ 考虑充电站排队与负荷
- ✅ 支持多种调度策略
- ✅ 支持多种问题规模

### 难度分（数据结构与算法）

- ✅ 图结构实现道路网络（邻接表）
- ✅ Dijkstra 最短路径算法
- ✅ A* 启发式搜索算法
- ✅ 优先队列实现
- ✅ 多种调度策略实现
- ✅ 事件驱动模拟

### 附加分

- ✅ 完整的图形界面
- ✅ 可视化地图画布
- ✅ 策略对比分析功能
- ✅ 实时统计和事件日志

## 🔧 扩展方向

### 进阶算法（可选实现）

1. **强化学习方法**：使用 Q-Learning 或 DQN 学习最优调度策略
2. **元启发式方法**：遗传算法、蚁群算法优化路径
3. **多智能体系统**：分布式调度决策

### Gurobi 精确求解（可选实现）

在上帝视角下，可以使用 Gurobi 求解器建立混合整数规划模型：

```python
# 示例模型
from gurobipy import *

# 决策变量
x[i,j,k] = 1 if 车辆k从节点i到节点j
t[i,k] = 车辆k到达节点i的时间

# 目标函数
minimize sum(cost * x) + penalty * delay

# 约束
# 流平衡约束、容量约束、时间窗约束等
```

## 📝 许可证

MIT License

## 👨‍💻 作者

数据结构课程小组作业
