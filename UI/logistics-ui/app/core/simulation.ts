// 模拟引擎 - 新能源物流车队协同调度系统核心逻辑

import {
  Vehicle,
  Task,
  ChargingStation,
  SimulationState,
  SimulationConfig,
  SimulationEvent,
  Statistics,
  SchedulingStrategy,
  ChargingStrategy,
  ProblemScale
} from '../types';
import { GraphManager, generateRandomNetwork } from './graph';

// 随机数生成器（支持种子）
class SeededRandom {
  private seed: number;

  constructor(seed: number = Date.now()) {
    this.seed = seed;
  }

  next(): number {
    this.seed = (this.seed * 1103515245 + 12345) & 0x7fffffff;
    return this.seed / 0x7fffffff;
  }

  nextInt(min: number, max: number): number {
    return Math.floor(this.next() * (max - min + 1)) + min;
  }

  nextFloat(min: number, max: number): number {
    return this.next() * (max - min) + min;
  }
}

// 预设问题规模
export const ProblemScales: ProblemScale[] = [
  {
    id: 'small',
    name: '小规模',
    description: '5辆车，15个节点，2个充电站',
    vehicleCount: 5,
    nodeCount: 15,
    chargingStationCount: 2,
    taskGenerationRate: 0.5,
    mapSize: 500
  },
  {
    id: 'medium',
    name: '中等规模',
    description: '10辆车，30个节点，4个充电站',
    vehicleCount: 10,
    nodeCount: 30,
    chargingStationCount: 4,
    taskGenerationRate: 1,
    mapSize: 800
  },
  {
    id: 'large',
    name: '大规模',
    description: '20辆车，50个节点，6个充电站',
    vehicleCount: 20,
    nodeCount: 50,
    chargingStationCount: 6,
    taskGenerationRate: 2,
    mapSize: 1200
  },
  {
    id: 'extreme',
    name: '超大规模',
    description: '30辆车，80个节点，10个充电站',
    vehicleCount: 30,
    nodeCount: 80,
    chargingStationCount: 10,
    taskGenerationRate: 3,
    mapSize: 1500
  }
];

// 车辆颜色
const VEHICLE_COLORS = [
  '#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6',
  '#EC4899', '#06B6D4', '#84CC16', '#F97316', '#6366F1',
  '#14B8A6', '#F43F5E', '#A855F7', '#22C55E', '#FACC15'
];

// 模拟引擎类
export class SimulationEngine {
  private state: SimulationState;
  private graphManager: GraphManager;
  private random: SeededRandom;
  private intervalId: NodeJS.Timeout | null = null;
  private onStateChange: ((state: SimulationState) => void) | null = null;
  private lastTaskGeneration: number = 0;

  constructor() {
    this.graphManager = new GraphManager();
    this.random = new SeededRandom();
    this.state = this.createInitialState();
  }

  // 创建初始状态
  private createInitialState(): SimulationState {
    return {
      status: 'idle',
      currentTime: 0,
      vehicles: [],
      tasks: [],
      chargingStations: [],
      warehouses: [],
      graph: { nodes: new Map(), edges: new Map() },
      statistics: this.createInitialStatistics(),
      config: this.createDefaultConfig(),
      eventLog: []
    };
  }

  // 创建初始统计数据
  private createInitialStatistics(): Statistics {
    return {
      totalTasks: 0,
      completedTasks: 0,
      failedTasks: 0,
      pendingTasks: 0,
      totalScore: 0,
      totalDistance: 0,
      averageDeliveryTime: 0,
      vehicleUtilization: 0,
      chargingStationUtilization: 0,
      onTimeRate: 0,
      collaborativeTasks: 0
    };
  }

  // 创建默认配置
  private createDefaultConfig(): SimulationConfig {
    return {
      scale: ProblemScales[1], // 默认中等规模
      strategy: 'nearest_first',
      chargingStrategy: 'optimal_station',
      simulationSpeed: 1,
      maxSimulationTime: 480, // 8小时
      enableCollaboration: false
    };
  }

  // 设置状态变化回调
  setOnStateChange(callback: (state: SimulationState) => void): void {
    this.onStateChange = callback;
  }

  // 通知状态变化
  private notifyStateChange(): void {
    if (this.onStateChange) {
      this.onStateChange({ ...this.state });
    }
  }

  // 初始化模拟
  initialize(config: SimulationConfig): void {
    this.state.config = config;
    this.random = new SeededRandom(config.randomSeed || Date.now());

    // 生成道路网络
    this.graphManager = generateRandomNetwork(
      config.scale.nodeCount,
      config.scale.mapSize,
      1,
      config.scale.chargingStationCount
    );

    // 初始化仓库
    this.initializeWarehouses();

    // 初始化充电站
    this.initializeChargingStations();

    // 初始化车辆
    this.initializeVehicles(config.scale.vehicleCount);

    // 重置统计数据
    this.state.statistics = this.createInitialStatistics();
    this.state.tasks = [];
    this.state.eventLog = [];
    this.state.currentTime = 0;
    this.state.status = 'idle';
    this.state.graph = this.graphManager.getGraph();
    this.lastTaskGeneration = 0;

    this.notifyStateChange();
  }

  // 初始化仓库
  private initializeWarehouses(): void {
    this.state.warehouses = [];
    const nodes = this.graphManager.getAllNodes();
    nodes.filter(n => n.type === 'warehouse').forEach((node, index) => {
      this.state.warehouses.push({
        id: `warehouse_${index}`,
        nodeId: node.id,
        position: node.position,
        name: node.name || `仓库 ${index + 1}`
      });
    });
  }

  // 初始化充电站
  private initializeChargingStations(): void {
    this.state.chargingStations = [];
    const nodes = this.graphManager.getAllNodes();
    nodes.filter(n => n.type === 'charging_station').forEach((node, index) => {
      this.state.chargingStations.push({
        id: `charging_${index}`,
        nodeId: node.id,
        position: node.position,
        name: node.name || `充电站 ${index + 1}`,
        capacity: 3,
        currentQueue: [],
        chargingVehicles: [],
        chargingSpeed: 10, // 每分钟充10%
        maxLoad: 100,
        currentLoad: 0
      });
    });
  }

  // 初始化车辆
  private initializeVehicles(count: number): void {
    this.state.vehicles = [];
    const warehouse = this.state.warehouses[0];
    if (!warehouse) return;

    for (let i = 0; i < count; i++) {
      this.state.vehicles.push({
        id: `vehicle_${i}`,
        name: `车辆 ${i + 1}`,
        position: { ...warehouse.position },
        currentNodeId: warehouse.nodeId,
        battery: 100,
        maxBattery: 100,
        batteryConsumption: 2, // 每公里耗2%电
        currentLoad: 0,
        maxLoad: 500 + this.random.nextInt(0, 500), // 500-1000kg
        status: 'idle',
        speed: 30 + this.random.nextInt(0, 20), // 30-50 km/h
        path: [],
        pathProgress: 0,
        assignedTasks: [],
        completedTasks: 0,
        totalDistance: 0,
        color: VEHICLE_COLORS[i % VEHICLE_COLORS.length]
      });
    }
  }

  // 开始模拟
  start(): void {
    if (this.state.status === 'running') return;
    this.state.status = 'running';
    this.notifyStateChange();

    const tickInterval = 100; // 100ms更新一次
    this.intervalId = setInterval(() => {
      this.tick(tickInterval * this.state.config.simulationSpeed / 60000); // 转换为模拟分钟
    }, tickInterval);
  }

  // 暂停模拟
  pause(): void {
    if (this.state.status !== 'running') return;
    this.state.status = 'paused';
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    this.notifyStateChange();
  }

  // 停止模拟
  stop(): void {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    this.state.status = 'idle';
    this.notifyStateChange();
  }

  // 重置模拟
  reset(): void {
    this.stop();
    this.initialize(this.state.config);
  }

  // 设置模拟速度
  setSpeed(speed: number): void {
    this.state.config.simulationSpeed = speed;
    this.notifyStateChange();
  }

  // 设置调度策略
  setStrategy(strategy: SchedulingStrategy): void {
    this.state.config.strategy = strategy;
    this.addEvent('strategy_changed', `调度策略变更为: ${this.getStrategyName(strategy)}`);
    this.notifyStateChange();
  }

  setChargingStrategy(strategy: ChargingStrategy): void {
    this.state.config.chargingStrategy = strategy;
    this.addEvent('strategy_changed', `充电策略变更为: ${this.getChargingStrategyName(strategy)}`);
    this.notifyStateChange();
  }

  // 获取策略名称
  getStrategyName(strategy: SchedulingStrategy): string {
    const names: Record<SchedulingStrategy, string> = {
      'nearest_first': '最近任务优先',
      'largest_first': '最大任务优先',
      'q_learning': 'Q-learning',
      'highest_reward': '最高收益优先',
      'earliest_deadline': '最早截止优先',
      'balanced': '均衡策略',
      'collaborative': '协同调度'
    };
    return names[strategy];
  }

  getChargingStrategyName(strategy: ChargingStrategy): string {
    const names: Record<ChargingStrategy, string> = {
      'optimal_station': '最优充电站',
      'nearest_station': '最近充电站',
    };
    return names[strategy];
  }

  // 模拟时钟滴答
  private tick(deltaMinutes: number): void {
    if (this.state.status !== 'running') return;

    this.state.currentTime += deltaMinutes;

    // 检查是否达到最大模拟时间
    if (this.state.currentTime >= this.state.config.maxSimulationTime) {
      this.state.status = 'completed';
      this.addEvent('task_completed', '模拟完成');
      if (this.intervalId) {
        clearInterval(this.intervalId);
        this.intervalId = null;
      }
      this.notifyStateChange();
      return;
    }

    // 生成新任务
    this.generateTasks(deltaMinutes);

    // 更新车辆状态
    this.updateVehicles(deltaMinutes);

    // 更新充电站状态
    this.updateChargingStations(deltaMinutes);

    // 检查并执行调度
    this.performScheduling();

    // 检查超时任务
    this.checkExpiredTasks();

    // 更新统计数据
    this.updateStatistics();

    this.notifyStateChange();
  }

  // 生成任务
  private generateTasks(deltaMinutes: number): void {
    this.lastTaskGeneration += deltaMinutes;
    const taskInterval = 1 / this.state.config.scale.taskGenerationRate;

    while (this.lastTaskGeneration >= taskInterval) {
      this.lastTaskGeneration -= taskInterval;
      this.createRandomTask();
    }
  }

  // 创建随机任务
  private createRandomTask(): void {
    const nodes = this.graphManager.getAllNodes().filter(n => n.type === 'intersection');
    if (nodes.length === 0) return;

    const targetNode = nodes[this.random.nextInt(0, nodes.length - 1)];
    const warehouse = this.state.warehouses[0];
    if (!warehouse) return;

    const weight = this.random.nextInt(50, 300); // 50-300kg
    const priority = this.getRandomPriority();
    const baseReward = weight * (priority === 'urgent' ? 3 : priority === 'high' ? 2 : priority === 'medium' ? 1.5 : 1);
    const deadline = this.state.currentTime + this.random.nextInt(30, 120); // 30-120分钟后截止

    const task: Task = {
      id: `task_${this.state.tasks.length}`,
      position: targetNode.position,
      nodeId: targetNode.id,
      weight,
      createTime: this.state.currentTime,
      deadline,
      status: 'pending',
      priority,
      reward: baseReward,
      pickupNodeId: warehouse.nodeId
    };

    this.state.tasks.push(task);
    this.state.statistics.totalTasks++;
    this.state.statistics.pendingTasks++;
    this.addEvent('task_created', `新任务生成: ${task.id}, 重量: ${weight}kg, 优先级: ${priority}`);
  }

  // 获取随机优先级
  private getRandomPriority(): Task['priority'] {
    const r = this.random.next();
    if (r < 0.1) return 'urgent';
    if (r < 0.3) return 'high';
    if (r < 0.6) return 'medium';
    return 'low';
  }

  // 更新车辆状态
  private updateVehicles(deltaMinutes: number): void {
    for (const vehicle of this.state.vehicles) {
      switch (vehicle.status) {
        case 'delivering':
        case 'returning':
          this.moveVehicle(vehicle, deltaMinutes);
          break;
        case 'charging':
          // 充电在充电站更新中处理
          break;
        case 'waiting':
          // 等待充电
          break;
        case 'idle':
          // 空闲状态
          break;
      }
    }
  }

  // 移动车辆
  private moveVehicle(vehicle: Vehicle, deltaMinutes: number): void {
    if (vehicle.path.length < 2) {
      // 到达目的地
      this.onVehicleArrived(vehicle);
      return;
    }

    const currentNode = this.graphManager.getNode(vehicle.path[0]);
    const nextNode = this.graphManager.getNode(vehicle.path[1]);
    if (!currentNode || !nextNode) return;

    const segmentDistance = GraphManager.euclideanDistance(currentNode.position, nextNode.position) / 100;
    const travelTime = segmentDistance / vehicle.speed * 60; // 分钟
    const progressIncrement = deltaMinutes / travelTime;

    vehicle.pathProgress += progressIncrement;

    // 更新位置（插值）
    vehicle.position = {
      x: currentNode.position.x + (nextNode.position.x - currentNode.position.x) * vehicle.pathProgress,
      y: currentNode.position.y + (nextNode.position.y - currentNode.position.y) * vehicle.pathProgress
    };

    // 消耗电量
    const distanceTraveled = segmentDistance * progressIncrement;
    vehicle.battery -= distanceTraveled * vehicle.batteryConsumption;
    vehicle.totalDistance += distanceTraveled;
    this.state.statistics.totalDistance += distanceTraveled;

    if (vehicle.pathProgress >= 1) {
      // 到达下一个节点
      vehicle.path.shift();
      vehicle.pathProgress = 0;
      vehicle.currentNodeId = nextNode.id;
      vehicle.position = { ...nextNode.position };

      if (vehicle.path.length <= 1) {
        this.onVehicleArrived(vehicle);
      }
    }
  }

  // 车辆到达目的地
  private onVehicleArrived(vehicle: Vehicle): void {
    const currentNode = this.graphManager.getNode(vehicle.currentNodeId);
    if (!currentNode) return;

    if (currentNode.type === 'charging_station') {
      // 到达充电站
      const station = this.state.chargingStations.find(s => s.nodeId === currentNode.id);
      if (station) {
        this.startCharging(vehicle, station);
      }
    } else if (vehicle.assignedTasks.length > 0) {
      // 完成配送任务
      const taskId = vehicle.assignedTasks[0];
      const task = this.state.tasks.find(t => t.id === taskId);
      
      if (task && vehicle.currentNodeId === task.nodeId) {
        this.completeTask(vehicle, task);
      } else if (task && vehicle.currentNodeId === task.pickupNodeId) {
        // 到达仓库，开始配送
        vehicle.currentLoad = task.weight;
        const pathResult = this.graphManager.dijkstra(vehicle.currentNodeId, task.nodeId);
        if (pathResult) {
          vehicle.path = pathResult.path;
          vehicle.pathProgress = 0;
          this.addEvent('vehicle_departed', `${vehicle.name} 开始配送任务 ${task.id}`);
        }
      }
    } else {
      // 返回仓库
      vehicle.status = 'idle';
      vehicle.path = [];
      this.addEvent('vehicle_arrived', `${vehicle.name} 返回仓库`);
    }
  }

  // 完成任务
  private completeTask(vehicle: Vehicle, task: Task): void {
    const deliveryTime = this.state.currentTime - task.createTime;
    const isOnTime = this.state.currentTime <= task.deadline;
    
    // 计算得分
    let score = task.reward;
    if (isOnTime) {
      // 提前完成有奖励
      const timeBonus = (task.deadline - this.state.currentTime) / (task.deadline - task.createTime);
      score *= (1 + timeBonus * 0.5);
    } else {
      // 超时扣分
      const overtimeRatio = (this.state.currentTime - task.deadline) / (task.deadline - task.createTime);
      score *= Math.max(0, 1 - overtimeRatio);
    }

    task.status = 'completed';
    task.completedTime = this.state.currentTime;
    vehicle.assignedTasks.shift();
    vehicle.currentLoad = 0;
    vehicle.completedTasks++;

    this.state.statistics.completedTasks++;
    this.state.statistics.pendingTasks--;
    this.state.statistics.totalScore += score;

    this.addEvent('task_completed', 
      `${vehicle.name} 完成任务 ${task.id}, 得分: ${score.toFixed(1)}, 用时: ${deliveryTime.toFixed(1)}分钟`
    );

    // 检查是否需要充电或继续任务
    if (vehicle.battery < 30) {
      this.sendToChargingStation(vehicle);
    } else if (vehicle.assignedTasks.length > 0) {
      // 还有任务，继续配送
      const nextTask = this.state.tasks.find(t => t.id === vehicle.assignedTasks[0]);
      if (nextTask) {
        const pathResult = this.graphManager.dijkstra(vehicle.currentNodeId, nextTask.pickupNodeId);
        if (pathResult) {
          vehicle.path = pathResult.path;
          vehicle.status = 'delivering';
        }
      }
    } else {
      // 返回仓库
      this.sendToWarehouse(vehicle);
    }
  }

  // 发送车辆去充电站
  private sendToChargingStation(vehicle: Vehicle): void {
    const chargingNodeIds = this.state.chargingStations.map(s => s.nodeId);
    const nearest = this.graphManager.findNearestChargingStation(vehicle.currentNodeId, chargingNodeIds);
    
    if (nearest) {
      const pathResult = this.graphManager.dijkstra(vehicle.currentNodeId, nearest.nodeId);
      if (pathResult) {
        vehicle.path = pathResult.path;
        vehicle.pathProgress = 0;
        vehicle.status = 'delivering';
        vehicle.targetNodeId = nearest.nodeId;
        this.addEvent('vehicle_departed', `${vehicle.name} 前往充电站`);
      }
    }
  }

  // 发送车辆回仓库
  private sendToWarehouse(vehicle: Vehicle): void {
    const warehouse = this.state.warehouses[0];
    if (!warehouse) return;

    if (vehicle.currentNodeId === warehouse.nodeId) {
      vehicle.status = 'idle';
      vehicle.path = [];
      return;
    }

    const pathResult = this.graphManager.dijkstra(vehicle.currentNodeId, warehouse.nodeId);
    if (pathResult) {
      vehicle.path = pathResult.path;
      vehicle.pathProgress = 0;
      vehicle.status = 'returning';
      this.addEvent('vehicle_departed', `${vehicle.name} 返回仓库`);
    }
  }

  // 开始充电
  private startCharging(vehicle: Vehicle, station: ChargingStation): void {
    if (station.chargingVehicles.length < station.capacity) {
      station.chargingVehicles.push(vehicle.id);
      vehicle.status = 'charging';
      this.addEvent('vehicle_charging', `${vehicle.name} 在 ${station.name} 开始充电`);
    } else {
      station.currentQueue.push(vehicle.id);
      vehicle.status = 'waiting';
      this.addEvent('vehicle_arrived', `${vehicle.name} 在 ${station.name} 排队等待充电`);
    }
  }

  // 更新充电站状态
  private updateChargingStations(deltaMinutes: number): void {
    for (const station of this.state.chargingStations) {
      // 更新正在充电的车辆
      const chargedVehicles: string[] = [];
      for (const vehicleId of station.chargingVehicles) {
        const vehicle = this.state.vehicles.find(v => v.id === vehicleId);
        if (vehicle) {
          vehicle.battery += station.chargingSpeed * deltaMinutes;
          if (vehicle.battery >= vehicle.maxBattery) {
            vehicle.battery = vehicle.maxBattery;
            chargedVehicles.push(vehicleId);
            vehicle.status = 'idle';
            this.addEvent('vehicle_charged', `${vehicle.name} 完成充电`);
            
            // 检查是否有待完成的任务
            if (vehicle.assignedTasks.length > 0) {
              const task = this.state.tasks.find(t => t.id === vehicle.assignedTasks[0]);
              if (task) {
                const pathResult = this.graphManager.dijkstra(vehicle.currentNodeId, task.pickupNodeId);
                if (pathResult) {
                  vehicle.path = pathResult.path;
                  vehicle.status = 'delivering';
                }
              }
            } else {
              this.sendToWarehouse(vehicle);
            }
          }
        }
      }

      // 移除已完成充电的车辆
      station.chargingVehicles = station.chargingVehicles.filter(id => !chargedVehicles.includes(id));

      // 让排队的车辆开始充电
      while (station.chargingVehicles.length < station.capacity && station.currentQueue.length > 0) {
        const nextVehicleId = station.currentQueue.shift()!;
        const vehicle = this.state.vehicles.find(v => v.id === nextVehicleId);
        if (vehicle) {
          station.chargingVehicles.push(nextVehicleId);
          vehicle.status = 'charging';
          this.addEvent('vehicle_charging', `${vehicle.name} 在 ${station.name} 开始充电`);
        }
      }

      // 更新负荷
      station.currentLoad = (station.chargingVehicles.length / station.capacity) * 100;
    }
  }

  // 执行调度
  private performScheduling(): void {
    const pendingTasks = this.state.tasks.filter(t => t.status === 'pending');
    const availableVehicles = this.state.vehicles.filter(
      v => v.status === 'idle' && v.battery > 30 && v.assignedTasks.length === 0
    );

    if (pendingTasks.length === 0 || availableVehicles.length === 0) return;

    const strategy = this.state.config.strategy;

    // 根据策略排序任务
    const sortedTasks = this.sortTasksByStrategy(pendingTasks, strategy);

    for (const vehicle of availableVehicles) {
      const task = this.selectTaskForVehicle(vehicle, sortedTasks, strategy);
      if (task) {
        this.assignTaskToVehicle(vehicle, task);
      }
    }
  }

  // 根据策略排序任务
  private sortTasksByStrategy(tasks: Task[], strategy: SchedulingStrategy): Task[] {
    const sorted = [...tasks];
    
    switch (strategy) {
      case 'nearest_first':
        // 在selectTaskForVehicle中处理，因为需要知道车辆位置
        break;
      case 'largest_first':
        sorted.sort((a, b) => b.weight - a.weight);
        break;
      case 'highest_reward':
        sorted.sort((a, b) => b.reward - a.reward);
        break;
      case 'earliest_deadline':
        sorted.sort((a, b) => a.deadline - b.deadline);
        break;
      case 'balanced':
        // 综合考虑多个因素
        sorted.sort((a, b) => {
          const scoreA = a.reward / (a.deadline - this.state.currentTime + 1);
          const scoreB = b.reward / (b.deadline - this.state.currentTime + 1);
          return scoreB - scoreA;
        });
        break;
      case 'collaborative':
        // 按重量排序，重的任务可能需要协作
        sorted.sort((a, b) => b.weight - a.weight);
        break;
    }

    return sorted;
  }

  // 为车辆选择任务
  private selectTaskForVehicle(vehicle: Vehicle, tasks: Task[], strategy: SchedulingStrategy): Task | null {
    const eligibleTasks = tasks.filter(t => 
      t.status === 'pending' && 
      t.weight <= vehicle.maxLoad - vehicle.currentLoad
    );

    if (eligibleTasks.length === 0) return null;

    if (strategy === 'nearest_first') {
      // 计算到每个任务的距离并选择最近的
      let nearestTask: Task | null = null;
      let shortestDistance = Infinity;

      for (const task of eligibleTasks) {
        const pathResult = this.graphManager.dijkstra(vehicle.currentNodeId, task.nodeId);
        if (pathResult && pathResult.distance < shortestDistance) {
          shortestDistance = pathResult.distance;
          nearestTask = task;
        }
      }

      return nearestTask;
    }

    // 对于其他策略，选择排序后的第一个符合条件的任务
    return eligibleTasks[0] || null;
  }

  // 分配任务给车辆
  private assignTaskToVehicle(vehicle: Vehicle, task: Task): void {
    // 检查电量是否足够
    const warehouseNode = this.state.warehouses[0]?.nodeId;
    if (!warehouseNode) return;

    const toWarehousePath = this.graphManager.dijkstra(vehicle.currentNodeId, warehouseNode);
    const toTaskPath = this.graphManager.dijkstra(warehouseNode, task.nodeId);
    const returnPath = this.graphManager.dijkstra(task.nodeId, warehouseNode);

    if (!toWarehousePath || !toTaskPath || !returnPath) return;

    const totalDistance = toWarehousePath.distance + toTaskPath.distance + returnPath.distance;
    const batteryNeeded = totalDistance * vehicle.batteryConsumption;

    if (batteryNeeded > vehicle.battery) {
      // 电量不足，先去充电
      this.sendToChargingStation(vehicle);
      vehicle.assignedTasks.push(task.id);
      task.status = 'assigned';
      task.assignedVehicleId = vehicle.id;
      return;
    }

    // 分配任务
    vehicle.assignedTasks.push(task.id);
    task.status = 'assigned';
    task.assignedVehicleId = vehicle.id;

    // 设置路径
    vehicle.path = toWarehousePath.path;
    vehicle.pathProgress = 0;
    vehicle.status = 'delivering';

    this.addEvent('task_assigned', `任务 ${task.id} 分配给 ${vehicle.name}`);
  }

  // 检查超时任务
  private checkExpiredTasks(): void {
    for (const task of this.state.tasks) {
      if (task.status === 'pending' && this.state.currentTime > task.deadline) {
        task.status = 'expired';
        this.state.statistics.failedTasks++;
        this.state.statistics.pendingTasks--;
        this.state.statistics.totalScore -= task.reward * 0.5; // 超时扣分
        this.addEvent('task_failed', `任务 ${task.id} 超时未完成`);
      }
    }
  }

  // 更新统计数据
  private updateStatistics(): void {
    const stats = this.state.statistics;
    
    // 计算准时率
    const completedTasks = this.state.tasks.filter(t => t.status === 'completed');
    if (completedTasks.length > 0) {
      const onTimeTasks = completedTasks.filter(t => 
        t.completedTime! <= t.deadline
      ).length;
      stats.onTimeRate = onTimeTasks / completedTasks.length * 100;

      // 计算平均配送时间
      const totalDeliveryTime = completedTasks.reduce((sum, t) => 
        sum + (t.completedTime! - t.createTime), 0
      );
      stats.averageDeliveryTime = totalDeliveryTime / completedTasks.length;
    }

    // 计算车辆利用率
    const busyVehicles = this.state.vehicles.filter(
      v => v.status !== 'idle'
    ).length;
    stats.vehicleUtilization = busyVehicles / this.state.vehicles.length * 100;

    // 计算充电站利用率
    const totalCharging = this.state.chargingStations.reduce(
      (sum, s) => sum + s.chargingVehicles.length + s.currentQueue.length, 0
    );
    const totalCapacity = this.state.chargingStations.reduce(
      (sum, s) => sum + s.capacity, 0
    );
    stats.chargingStationUtilization = totalCapacity > 0 ? totalCharging / totalCapacity * 100 : 0;

    // 更新待处理任务数
    stats.pendingTasks = this.state.tasks.filter(
      t => t.status === 'pending' || t.status === 'assigned' || t.status === 'in_progress'
    ).length;
  }

  // 添加事件日志
  private addEvent(type: SimulationEvent['type'], message: string, details?: Record<string, unknown>): void {
    const event: SimulationEvent = {
      id: `event_${this.state.eventLog.length}`,
      time: this.state.currentTime,
      type,
      message,
      details
    };
    this.state.eventLog.push(event);

    // 限制日志数量
    if (this.state.eventLog.length > 100) {
      this.state.eventLog = this.state.eventLog.slice(-100);
    }
  }

  // 获取当前状态
  getState(): SimulationState {
    return { ...this.state };
  }

  // 获取图管理器
  getGraphManager(): GraphManager {
    return this.graphManager;
  }

  // 手动创建任务
  createTask(nodeId: string, weight: number, priority: Task['priority']): void {
    const node = this.graphManager.getNode(nodeId);
    const warehouse = this.state.warehouses[0];
    if (!node || !warehouse) return;

    const baseReward = weight * (priority === 'urgent' ? 3 : priority === 'high' ? 2 : priority === 'medium' ? 1.5 : 1);
    const deadline = this.state.currentTime + 60; // 1小时后截止

    const task: Task = {
      id: `task_${this.state.tasks.length}`,
      position: node.position,
      nodeId: node.id,
      weight,
      createTime: this.state.currentTime,
      deadline,
      status: 'pending',
      priority,
      reward: baseReward,
      pickupNodeId: warehouse.nodeId
    };

    this.state.tasks.push(task);
    this.state.statistics.totalTasks++;
    this.state.statistics.pendingTasks++;
    this.addEvent('task_created', `手动添加任务: ${task.id}, 重量: ${weight}kg`);
    this.notifyStateChange();
  }

  // 启用/禁用协同调度
  setCollaboration(enabled: boolean): void {
    this.state.config.enableCollaboration = enabled;
    this.notifyStateChange();
  }
}

// 导出单例
let engineInstance: SimulationEngine | null = null;

export function getSimulationEngine(): SimulationEngine {
  if (!engineInstance) {
    engineInstance = new SimulationEngine();
  }
  return engineInstance;
}

export function resetSimulationEngine(): void {
  if (engineInstance) {
    engineInstance.stop();
  }
  engineInstance = new SimulationEngine();
}
