// 新能源物流车队协同调度系统 - 类型定义

// 坐标点
export interface Point {
  x: number;
  y: number;
}

// 道路节点
export interface Node {
  id: string;
  position: Point;
  type: 'intersection' | 'warehouse' | 'charging_station' | 'delivery_point';
  name?: string;
}

// 道路边
export interface Edge {
  id: string;
  from: string;
  to: string;
  distance: number; // 距离（公里）
  trafficFactor: number; // 交通系数（1为正常，>1表示拥堵）
}

// 图结构
export interface Graph {
  nodes: Map<string, Node>;
  edges: Map<string, Edge[]>; // 邻接表
}

// 车辆状态
export type VehicleStatus = 'idle' | 'delivering' | 'charging' | 'returning' | 'waiting';

// 车辆
export interface Vehicle {
  id: string;
  name: string;
  position: Point;
  currentNodeId: string;
  targetNodeId?: string;
  battery: number; // 当前电量 (0-100)
  maxBattery: number; // 最大电量
  batteryConsumption: number; // 每公里耗电量
  currentLoad: number; // 当前载重 (kg)
  maxLoad: number; // 最大载重 (kg)
  status: VehicleStatus;
  speed: number; // 速度 (km/h)
  path: string[]; // 当前路径节点ID列表
  pathProgress: number; // 路径进度 (0-1)
  assignedTasks: string[]; // 已分配任务ID
  completedTasks: number; // 完成任务数
  totalDistance: number; // 总行驶距离
  color: string; // 显示颜色
}

// 任务状态
export type TaskStatus = 'pending' | 'assigned' | 'in_progress' | 'completed' | 'failed' | 'expired';

// 任务优先级
export type TaskPriority = 'low' | 'medium' | 'high' | 'urgent';

// 配送任务
export interface Task {
  id: string;
  position: Point;
  nodeId: string;
  weight: number; // 货物重量 (kg)
  createTime: number; // 任务产生时间（模拟时间戳）
  deadline: number; // 截止时间（模拟时间戳）
  status: TaskStatus;
  priority: TaskPriority;
  reward: number; // 基础奖励分数
  assignedVehicleId?: string;
  completedTime?: number;
  pickupNodeId: string; // 取货地点（仓库）
}

// 充电站
export interface ChargingStation {
  id: string;
  nodeId: string;
  position: Point;
  name: string;
  capacity: number; // 充电桩数量
  currentQueue: string[]; // 排队车辆ID
  chargingVehicles: string[]; // 正在充电的车辆ID
  chargingSpeed: number; // 充电速度 (%/分钟)
  maxLoad: number; // 最大负荷
  currentLoad: number; // 当前负荷
}

// 仓库
export interface Warehouse {
  id: string;
  nodeId: string;
  position: Point;
  name: string;
}

// 调度策略
export type SchedulingStrategy = 
  | 'nearest_first' // 最近任务优先
  | 'largest_first' // 最大任务优先（货物最重）
  | 'earliest_deadline' // 最早截止时间优先
  | 'q_learning' // Q-learning 策略
  | 'highest_reward' // 前端本地演示策略
  | 'balanced' // 前端本地演示策略
  | 'collaborative'; // 前端本地演示策略

export type ChargingStrategy = 'optimal_station' | 'nearest_station';

// 问题规模
export interface ProblemScale {
  id: string;
  name: string;
  description: string;
  vehicleCount: number;
  nodeCount: number;
  chargingStationCount: number;
  taskGenerationRate: number; // 任务生成速率（每分钟）
  mapSize: number; // 地图大小
}

// 模拟状态
export type SimulationStatus = 'idle' | 'running' | 'paused' | 'completed';

// 模拟配置
export interface SimulationConfig {
  scale: ProblemScale;
  strategy: SchedulingStrategy;
  chargingStrategy: ChargingStrategy;
  simulationSpeed: number; // 模拟速度倍率
  maxSimulationTime: number; // 最大模拟时间（分钟）
  enableCollaboration: boolean; // 启用多车协作
  randomSeed?: number; // 随机种子
}

// 统计数据
export interface Statistics {
  totalTasks: number;
  completedTasks: number;
  failedTasks: number;
  pendingTasks: number;
  totalScore: number;
  totalDistance: number;
  averageDeliveryTime: number;
  vehicleUtilization: number; // 车辆利用率
  chargingStationUtilization: number; // 充电站利用率
  onTimeRate: number; // 准时率
  collaborativeTasks: number; // 协作完成的任务数
}

// 模拟状态
export interface SimulationState {
  status: SimulationStatus;
  currentTime: number; // 当前模拟时间（分钟）
  vehicles: Vehicle[];
  tasks: Task[];
  chargingStations: ChargingStation[];
  warehouses: Warehouse[];
  graph: Graph;
  statistics: Statistics;
  config: SimulationConfig;
  eventLog: SimulationEvent[];
}

// 模拟事件
export interface SimulationEvent {
  id: string;
  time: number;
  type: 'task_created' | 'task_assigned' | 'task_completed' | 'task_failed' | 
        'vehicle_departed' | 'vehicle_arrived' | 'vehicle_charging' | 'vehicle_charged' |
        'collaboration_started' | 'strategy_changed';
  message: string;
  details?: Record<string, unknown>;
}

// 路径结果
export interface PathResult {
  path: string[];
  distance: number;
  estimatedTime: number; // 预计时间（分钟）
  batteryRequired: number; // 需要电量
}

// 调度决策
export interface SchedulingDecision {
  vehicleId: string;
  taskId: string;
  path: PathResult;
  needsCharging: boolean;
  chargingStationId?: string;
  collaborators?: string[]; // 协作车辆
}

export interface RLModelState {
  modelLoaded: boolean;
  trainedEpisodes: number;
  currentReward: number;
  epsilon: number;
}
