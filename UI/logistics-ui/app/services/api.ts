// API服务层 - 与Python后端对接
// 本文件定义了前端与后端通信的接口

import { 
  SimulationState, 
  SimulationConfig, 
  Task, 
  Vehicle, 
  SchedulingStrategy,
  Statistics,
  PathResult 
} from '../types';

// API 配置
const API_CONFIG = {
  // Python后端地址，动态适配局域网访问
  BASE_URL: process.env.NEXT_PUBLIC_API_URL || (typeof window !== 'undefined' ? `http://${window.location.hostname}:8000` : 'http://localhost:8000'),
  // API 版本
  VERSION: 'v1',
  // 超时时间（毫秒）
  TIMEOUT: 30000,
};

// API 响应类型
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  timestamp: number;
}

// 路径规划请求
export interface PathPlanningRequest {
  startNodeId: string;
  endNodeId: string;
  vehicleId?: string;
  algorithm?: 'dijkstra' | 'astar' | 'genetic' | 'aco'; // 支持多种算法
}

// 调度决策请求
export interface SchedulingRequest {
  tasks: Task[];
  vehicles: Vehicle[];
  strategy: SchedulingStrategy;
  chargingStrategy?: SimulationConfig['chargingStrategy'];
  enableCollaboration?: boolean;
}

// 调度决策响应
export interface SchedulingResponse {
  assignments: {
    vehicleId: string;
    taskId: string;
    path: string[];
    estimatedTime: number;
    needsCharging: boolean;
  }[];
  score: number;
  executionTime: number;
}

// Gurobi 求解请求
export interface GurobiSolveRequest {
  tasks: Task[];
  vehicles: Vehicle[];
  graphData: {
    nodes: Array<{ id: string; x: number; y: number; type: string }>;
    edges: Array<{ from: string; to: string; distance: number }>;
  };
  timeLimit?: number; // 求解时间限制（秒）
}

export interface OfflineSolveRequest {
  scale: SimulationConfig['scale'];
  maxSimulationTime: number;
  solver?: 'gurobi' | 'cplex';
  chargeMode?: 'linear' | 'piecewise';
  timeLimit?: number;
}

export interface OfflineSolveResponse {
  simulationId: string;
  summaryJson: string;
  summaryCsv: string;
  routeCsv: string;
  objective: number;
  status: string;
  requestedScale?: string;
  actualScale?: string;
  fallbackApplied?: boolean;
}

// Gurobi 求解响应
export interface GurobiSolveResponse {
  optimalScore: number;
  assignments: {
    vehicleId: string;
    route: string[];
    tasks: string[];
    totalDistance: number;
  }[];
  gap: number; // 最优性间隙
  solveTime: number;
  status: 'optimal' | 'feasible' | 'infeasible' | 'timeout';
}

// 强化学习模型状态
export interface RLModelState {
  modelLoaded: boolean;
  trainedEpisodes: number;
  currentReward: number;
  epsilon: number; // 探索率
}

// API 客户端类
class ApiClient {
  private baseUrl: string;
  private timeout: number;

  constructor() {
    this.baseUrl = `${API_CONFIG.BASE_URL}/api/${API_CONFIG.VERSION}`;
    this.timeout = API_CONFIG.TIMEOUT;
  }

  // 通用请求方法
  private async request<T>(
    endpoint: string,
    method: 'GET' | 'POST' | 'PUT' | 'DELETE' = 'GET',
    body?: object,
    timeoutMs?: number
  ): Promise<ApiResponse<T>> {
    const controller = new AbortController();
    const effectiveTimeout = timeoutMs ?? this.timeout;
    const timeoutId = setTimeout(() => controller.abort(), effectiveTimeout);

    try {
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        method,
        headers: {
          'Content-Type': 'application/json',
        },
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        let errorMessage = `HTTP error! status: ${response.status}`;
        try {
          const errorPayload = await response.json();
          if (errorPayload && typeof errorPayload.detail === 'string' && errorPayload.detail.trim()) {
            errorMessage = errorPayload.detail;
          }
        } catch {
          // ignore json parse failure and keep status message
        }
        throw new Error(errorMessage);
      }

      const data = await response.json();
      return {
        success: true,
        data,
        timestamp: Date.now(),
      };
    } catch (error) {
      clearTimeout(timeoutId);
      const isAbort = error instanceof Error && error.name === 'AbortError';
      return {
        success: false,
        error: isAbort ? `请求超时（>${Math.round(effectiveTimeout / 1000)}秒）` : error instanceof Error ? error.message : 'Unknown error',
        timestamp: Date.now(),
      };
    }
  }

  // =============== 健康检查 ===============
  async healthCheck(): Promise<ApiResponse<{ status: string; version: string }>> {
    return this.request('/health');
  }

  // =============== 路径规划 API ===============
  
  // 使用后端算法计算路径
  async calculatePath(request: PathPlanningRequest): Promise<ApiResponse<PathResult>> {
    return this.request('/path/calculate', 'POST', request);
  }

  // 批量计算多条路径
  async calculatePaths(
    requests: PathPlanningRequest[]
  ): Promise<ApiResponse<PathResult[]>> {
    return this.request('/path/batch', 'POST', { paths: requests });
  }

  // =============== 调度 API ===============

  // 请求调度决策
  async getSchedulingDecision(
    request: SchedulingRequest
  ): Promise<ApiResponse<SchedulingResponse>> {
    return this.request('/scheduling/decide', 'POST', request);
  }

  // 获取所有调度策略的对比结果
  async compareStrategies(
    tasks: Task[],
    vehicles: Vehicle[]
  ): Promise<ApiResponse<Record<SchedulingStrategy, Statistics>>> {
    return this.request('/scheduling/compare', 'POST', { tasks, vehicles });
  }

  // =============== Gurobi 精确求解 ===============

  // 使用Gurobi求解全局最优
  async solveWithGurobi(
    request: GurobiSolveRequest
  ): Promise<ApiResponse<GurobiSolveResponse>> {
    return this.request('/solver/gurobi', 'POST', request);
  }

  async startOfflineSolve(
    request: OfflineSolveRequest
  ): Promise<ApiResponse<OfflineSolveResponse>> {
    return this.request('/solver/offline/start', 'POST', request, 300000);
  }

  // 获取Gurobi求解状态（长时间运行时）
  async getGurobiStatus(taskId: string): Promise<ApiResponse<{
    status: 'running' | 'completed' | 'failed';
    progress: number;
    currentBound?: number;
    bestSolution?: number;
  }>> {
    return this.request(`/solver/gurobi/status/${taskId}`);
  }

  // =============== 强化学习 API ===============

  // 获取RL模型状态
  async getRLModelState(): Promise<ApiResponse<RLModelState>> {
    return this.request('/rl/state');
  }

  // 使用RL模型进行决策
  async getRLDecision(
    state: SimulationState
  ): Promise<ApiResponse<SchedulingResponse>> {
    return this.request('/rl/decide', 'POST', { state });
  }

  // 训练RL模型
  async trainRLModel(episodes: number): Promise<ApiResponse<{
    trainedEpisodes: number;
    finalReward: number;
    trainingTime: number;
  }>> {
    return this.request('/rl/train', 'POST', { episodes });
  }

  // =============== 模拟控制 ===============

  // 开始后端模拟（用于精确算法）
  async startSimulation(
    config: SimulationConfig
  ): Promise<ApiResponse<{ simulationId: string }>> {
    return this.request('/simulation/start', 'POST', config);
  }

  // 获取模拟状态
  async getSimulationState(
    simulationId: string
  ): Promise<ApiResponse<SimulationState>> {
    return this.request(`/simulation/${simulationId}/state`);
  }

  // 停止模拟
  async stopSimulation(
    simulationId: string
  ): Promise<ApiResponse<{ stopped: boolean }>> {
    return this.request(`/simulation/${simulationId}/stop`, 'POST');
  }

  // 暂停模拟
  async pauseSimulation(
    simulationId: string
  ): Promise<ApiResponse<{ paused: boolean }>> {
    return this.request(`/simulation/${simulationId}/pause`, 'POST');
  }

  // 恢复模拟
  async resumeSimulation(
    simulationId: string
  ): Promise<ApiResponse<{ resumed: boolean }>> {
    return this.request(`/simulation/${simulationId}/resume`, 'POST');
  }

  // =============== 数据导出 ===============

  // 导出模拟结果
  async exportResults(
    simulationId: string,
    format: 'json' | 'csv' | 'excel'
  ): Promise<ApiResponse<{ downloadUrl: string }>> {
    return this.request(`/export/${simulationId}`, 'POST', { format });
  }
}

// 导出单例
export const apiClient = new ApiClient();

// =============== WebSocket 实时通信 ===============

export class RealtimeConnection {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private listeners: Map<string, ((data: unknown) => void)[]> = new Map();
  private intentionalClose = false;

  private buildWsUrl(): string {
    const base = new URL(API_CONFIG.BASE_URL);
    const protocol = base.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${base.host}/ws`;
  }

  connect(): Promise<void> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return Promise.resolve();
    }

    if (this.ws && this.ws.readyState === WebSocket.CONNECTING) {
      return Promise.resolve();
    }

    this.intentionalClose = false;

    return new Promise((resolve, reject) => {
      const wsUrl = this.buildWsUrl();
      let settled = false;

      const safeResolve = () => {
        if (!settled) {
          settled = true;
          resolve();
        }
      };

      const safeReject = (error: unknown) => {
        if (!settled) {
          settled = true;
          reject(error);
        }
      };
      
      try {
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
          console.log('WebSocket connected');
          this.reconnectAttempts = 0;
          safeResolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            const { type, data } = message;
            
            const typeListeners = this.listeners.get(type) || [];
            typeListeners.forEach(listener => listener(data));
          } catch (e) {
            console.error('Failed to parse WebSocket message:', e);
          }
        };

        this.ws.onclose = () => {
          console.log('WebSocket closed');
          this.ws = null;
          if (!this.intentionalClose) {
            this.attemptReconnect();
          }
        };

        this.ws.onerror = (error) => {
          console.warn('WebSocket error:', error);
          safeReject(new Error(`WebSocket connection failed: ${wsUrl}`));
        };
      } catch (error) {
        safeReject(error);
      }
    });
  }

  private attemptReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(`Attempting to reconnect... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
      setTimeout(() => this.connect(), 2000 * this.reconnectAttempts);
    }
  }

  // 订阅消息类型
  on(type: string, callback: (data: unknown) => void) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, []);
    }
    this.listeners.get(type)!.push(callback);
  }

  // 取消订阅
  off(type: string, callback: (data: unknown) => void) {
    const typeListeners = this.listeners.get(type);
    if (typeListeners) {
      const index = typeListeners.indexOf(callback);
      if (index > -1) {
        typeListeners.splice(index, 1);
      }
    }
  }

  // 发送消息
  send(type: string, data: unknown) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, data }));
    }
  }

  // 断开连接
  disconnect() {
    if (this.ws) {
      this.intentionalClose = true;
      this.ws.close();
      this.ws = null;
    }
  }
}

// 导出实时连接单例
export const realtimeConnection = new RealtimeConnection();
