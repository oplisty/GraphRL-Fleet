'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { SimulationState, SchedulingStrategy, ProblemScale, Node, Edge } from './types';
import { SimulationEngine, ProblemScales, getSimulationEngine } from './core/simulation';
import {
  AMapRealtimeMap,
  MapCanvas,
  VehiclePanel,
  TaskPanel,
  ChargingStationPanel,
  ControlPanel,
  StatisticsPanel
} from './components';
import { LoginModal, UserProfile, useAuth } from './components/LoginModal';
import { LeaderboardPanel } from './components/Leaderboard';
import { apiClient, realtimeConnection } from './services/api';
import { getAuthService } from './services/auth';

const USE_REMOTE_ENGINE = process.env.NEXT_PUBLIC_USE_ENGINE_BACKEND === '1';

function buildDefaultState(): SimulationState {
  return {
    status: 'idle',
    currentTime: 0,
    vehicles: [],
    tasks: [],
    chargingStations: [],
    warehouses: [],
    graph: { nodes: new Map(), edges: new Map() },
    statistics: {
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
      collaborativeTasks: 0,
    },
    config: {
      scale: ProblemScales[1],
      strategy: 'nearest_first',
      simulationSpeed: 1,
      maxSimulationTime: 480,
      enableCollaboration: false,
    },
    eventLog: [],
  };
}

function normalizeRemoteState(raw: unknown, fallback: SimulationState): SimulationState {
  if (!raw || typeof raw !== 'object') {
    return fallback;
  }

  const payload = raw as Record<string, unknown>;
  const graphRaw = (payload.graph as Record<string, unknown> | undefined) || {};

  const nodeList = Array.isArray(graphRaw.nodes) ? graphRaw.nodes : [];
  const edgeList = Array.isArray(graphRaw.edges) ? graphRaw.edges : [];

  const nodeMap = new Map<string, Node>();
  for (const node of nodeList) {
    const n = node as Record<string, unknown>;
    const id = String(n.id ?? '');
    const position = (n.position as Record<string, unknown> | undefined) || {};
    const rawType = String(n.type ?? 'intersection');
    const nodeType: Node['type'] =
      rawType === 'warehouse' ||
      rawType === 'charging_station' ||
      rawType === 'delivery_point' ||
      rawType === 'intersection'
        ? rawType
        : 'intersection';
    nodeMap.set(id, {
      id,
      position: {
        x: Number(position.x ?? 0),
        y: Number(position.y ?? 0),
      },
      type: nodeType,
      name: (n.name as string) || undefined,
    });
  }

  const edgeMap = new Map<string, Edge[]>();
  for (const edge of edgeList) {
    const e = edge as Record<string, unknown>;
    const from = String(e.from ?? '');
    const next = {
      id: String(e.id ?? `${from}_${String(e.to ?? '')}`),
      from,
      to: String(e.to ?? ''),
      distance: Number(e.distance ?? 0),
      trafficFactor: Number(e.trafficFactor ?? 1),
    };
    const existed = edgeMap.get(from) || [];
    existed.push(next);
    edgeMap.set(from, existed);
  }

  const nextState: SimulationState = {
    status: (payload.status as SimulationState['status']) || fallback.status,
    currentTime: Number(payload.currentTime ?? fallback.currentTime),
    vehicles: (Array.isArray(payload.vehicles) ? payload.vehicles : fallback.vehicles) as SimulationState['vehicles'],
    tasks: (Array.isArray(payload.tasks) ? payload.tasks : fallback.tasks) as SimulationState['tasks'],
    chargingStations: (
      Array.isArray(payload.chargingStations) ? payload.chargingStations : fallback.chargingStations
    ) as SimulationState['chargingStations'],
    warehouses: (Array.isArray(payload.warehouses) ? payload.warehouses : fallback.warehouses) as SimulationState['warehouses'],
    graph: {
      nodes: nodeMap,
      edges: edgeMap,
    },
    statistics: (payload.statistics as SimulationState['statistics']) || fallback.statistics,
    config: (payload.config as SimulationState['config']) || fallback.config,
    eventLog: (Array.isArray(payload.eventLog) ? payload.eventLog : fallback.eventLog) as SimulationState['eventLog'],
  };

  return nextState;
}

export default function Home() {
  const engineRef = useRef<SimulationEngine | null>(null);
  const [state, setState] = useState<SimulationState | null>(() =>
    USE_REMOTE_ENGINE ? buildDefaultState() : null
  );
  const [remoteSimulationId, setRemoteSimulationId] = useState<string | null>(null);
  const remoteSimulationIdRef = useRef<string | null>(null);
  const remoteListenerRef = useRef<((data: unknown) => void) | null>(null);
  const [selectedVehicleId, setSelectedVehicleId] = useState<string | undefined>();
  const [activeTab, setActiveTab] = useState<'vehicles' | 'tasks' | 'stations'>('vehicles');
  const [isInitialized, setIsInitialized] = useState(false);

  // 登录状态
  const { user, login, logout } = useAuth();
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [showLeaderboard, setShowLeaderboard] = useState(false);

  // 离线日志记录与回放状态
  const [showOfflineModal, setShowOfflineModal] = useState(false);
  const [offlineLogText, setOfflineLogText] = useState("");
  const offlineTimeRef = useRef<NodeJS.Timeout | null>(null);

  // 游戏结束时提交成绩
  const gameEndSubmittedRef = useRef(false);

  useEffect(() => {
    remoteSimulationIdRef.current = remoteSimulationId;
  }, [remoteSimulationId]);

  // 初始化模拟引擎（本地/远端双模式）
  useEffect(() => {
    if (USE_REMOTE_ENGINE) {
      const defaultState = buildDefaultState();
      const listener = (data: unknown) => {
        setState((prev) => normalizeRemoteState(data, prev ?? defaultState));
      };
      remoteListenerRef.current = listener;
      realtimeConnection.on('simulation_state', listener);
      realtimeConnection.connect().catch((err) => {
        console.error('Realtime connection failed:', err);
      });

      queueMicrotask(() => setIsInitialized(true));

      return () => {
        if (remoteListenerRef.current) {
          realtimeConnection.off('simulation_state', remoteListenerRef.current);
        }
        realtimeConnection.disconnect();
        const simId = remoteSimulationIdRef.current;
        if (simId) {
          apiClient.stopSimulation(simId).catch(() => undefined);
        }
      };
    }

    const engine = getSimulationEngine();
    engineRef.current = engine;

    // 设置状态变化回调
    engine.setOnStateChange((newState) => {
      setState({ ...newState });
    });

    // 初始化默认配置
    engine.initialize({
      scale: ProblemScales[1], // 中等规模
      strategy: 'nearest_first',
      simulationSpeed: 1,
      maxSimulationTime: 480,
      enableCollaboration: false
    });

    queueMicrotask(() => setIsInitialized(true));

    return () => {
      engine.stop();
    };
  }, []);

  // 游戏结束时提交成绩
  useEffect(() => {
    if (state?.status === 'completed' && user && state.statistics.completedTasks > 0 && !gameEndSubmittedRef.current) {
      gameEndSubmittedRef.current = true;
      const authService = getAuthService();
      authService.submitGameRecord({
        oderId: user.id,
        score: state.statistics.totalScore,
        completedTasks: state.statistics.completedTasks,
        failedTasks: state.statistics.failedTasks,
        onTimeRate: state.statistics.onTimeRate,
        totalDistance: state.statistics.totalDistance,
        strategy: state.config.strategy,
        scale: state.config.scale.name,
        duration: state.currentTime
      });
    }
    // 重置游戏时清除提交标记
    if (state?.status === 'idle') {
      gameEndSubmittedRef.current = false;
    }
  }, [state?.status, user, state?.statistics, state?.config, state?.currentTime]);

  // 控制函数
  const handleStart = useCallback(async () => {
    if (!state) return;

    if (!USE_REMOTE_ENGINE) {
      engineRef.current?.start();
      return;
    }

    if (remoteSimulationId && state.status === 'paused') {
      await apiClient.resumeSimulation(remoteSimulationId);
      return;
    }

    if (remoteSimulationId) {
      await apiClient.stopSimulation(remoteSimulationId);
      setRemoteSimulationId(null);
    }

    const started = await apiClient.startSimulation(state.config);
    if (!started.success || !started.data?.simulationId) {
      console.error('Failed to start remote simulation:', started.error);
      return;
    }

    const simulationId = started.data.simulationId;
    setRemoteSimulationId(simulationId);
    realtimeConnection.send('subscribe', { simulationId });
  }, [remoteSimulationId, state]);

  const handlePause = useCallback(async () => {
    if (!USE_REMOTE_ENGINE) {
      engineRef.current?.pause();
      return;
    }
    if (!remoteSimulationId) return;
    await apiClient.pauseSimulation(remoteSimulationId);
  }, [remoteSimulationId]);

  const handleStop = useCallback(async () => {
    if (!USE_REMOTE_ENGINE) {
      engineRef.current?.stop();
      return;
    }
    if (!remoteSimulationId) return;
    await apiClient.stopSimulation(remoteSimulationId);
    realtimeConnection.send('unsubscribe', { simulationId: remoteSimulationId });
    setRemoteSimulationId(null);
    setState((prev) => {
      if (!prev) return prev;
      return { ...prev, status: 'idle' };
    });
  }, [remoteSimulationId]);

  const handleReset = useCallback(async () => {
    if (!USE_REMOTE_ENGINE) {
      engineRef.current?.reset();
      return;
    }

    if (remoteSimulationId) {
      await apiClient.stopSimulation(remoteSimulationId);
      realtimeConnection.send('unsubscribe', { simulationId: remoteSimulationId });
      setRemoteSimulationId(null);
    }
    setState((prev) => {
      if (!prev) return prev;
      return { ...buildDefaultState(), config: prev.config };
    });
  }, [remoteSimulationId]);

  const handleSpeedChange = useCallback((speed: number) => {
    if (USE_REMOTE_ENGINE) {
      setState((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          config: {
            ...prev.config,
            simulationSpeed: speed,
          },
        };
      });
      return;
    }
    engineRef.current?.setSpeed(speed);
  }, []);

  const handleStrategyChange = useCallback((strategy: SchedulingStrategy) => {
    if (USE_REMOTE_ENGINE) {
      setState((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          config: {
            ...prev.config,
            strategy,
          },
        };
      });
      return;
    }
    engineRef.current?.setStrategy(strategy);
  }, []);

  const handleScaleChange = useCallback((scale: ProblemScale) => {
    if (USE_REMOTE_ENGINE) {
      setState((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          config: {
            ...prev.config,
            scale,
          },
        };
      });
      return;
    }
    const engine = engineRef.current;
    if (engine) {
      engine.initialize({
        ...engine.getState().config,
        scale
      });
    }
  }, []);

  const handleCollaborationChange = useCallback((enabled: boolean) => {
    if (USE_REMOTE_ENGINE) {
      setState((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          config: {
            ...prev.config,
            enableCollaboration: enabled,
          },
        };
      });
      return;
    }
    engineRef.current?.setCollaboration(enabled);
  }, []);

  const handleNodeClick = useCallback((nodeId: string) => {
    // 可以在这里添加点击节点的交互，比如手动创建任务
    console.log('Node clicked:', nodeId);
  }, []);

  const handleOfflineReplay = useCallback(() => {
    setShowOfflineModal(true);
  }, []);

  const handlePlayOffline = useCallback(() => {
    try {
      const logs = JSON.parse(offlineLogText);
      if (!Array.isArray(logs) || logs.length === 0) {
        alert("无效的离线日志格式，需要为数组");
        return;
      }
      setShowOfflineModal(false);
      
      let i = 0;
      if (offlineTimeRef.current) clearInterval(offlineTimeRef.current);
      
      if (remoteSimulationIdRef.current) {
        apiClient.stopSimulation(remoteSimulationIdRef.current);
        setRemoteSimulationId(null);
      }
      
      // 以稍快的速度回放，达到高帧率
      offlineTimeRef.current = setInterval(() => {
        if (i < logs.length) {
          // 这里如果是单纯的回放，可以根据日志更新 state，注意补充必要的图结构等防御
          setState((prev) => normalizeRemoteState(logs[i], prev ?? buildDefaultState()));
          i++;
        } else {
          if (offlineTimeRef.current) clearInterval(offlineTimeRef.current);
        }
      }, 50); // 更短间隔，更高帧率
    } catch(e) {
      alert("解析失败，请检查复制的内容: " + String(e));
    }
  }, [offlineLogText]);

  // 加载状态
  if (!isInitialized || !state) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-400 text-lg">加载中...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white particle-bg">
      {/* 顶部导航栏 */}
      <header className="bg-gray-900/90 backdrop-blur border-b border-gray-800 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 via-cyan-400 to-green-400 bg-clip-text text-transparent">
              🔋 新能源物流车队协同调度系统
            </h1>
            <span className="px-3 py-1 bg-gradient-to-r from-blue-600/20 to-cyan-600/20 border border-blue-500/30 rounded-full text-xs text-blue-300 animate-borderGradient">
              v1.0.0
            </span>
          </div>
          <div className="flex items-center gap-4">
            {/* 快速统计 */}
            <div className="px-3 py-1.5 bg-gray-800/50 rounded-lg border border-gray-700 text-sm">
              <span className="text-gray-400 mr-2">准时率</span>
              <span className="text-green-400 font-semibold">{state.statistics.onTimeRate.toFixed(0)}%</span>
            </div>
            
            {/* 排行榜按钮 */}
            <button
              onClick={() => setShowLeaderboard(true)}
              className="px-4 py-2 bg-gradient-to-r from-yellow-600 to-orange-600 hover:from-yellow-500 hover:to-orange-500 rounded-lg text-sm flex items-center gap-2 transition-all shadow-lg shadow-orange-500/20"
            >
              🏆 排行榜
            </button>
            
            <Link
              href="/compare"
              className="px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 rounded-lg text-sm flex items-center gap-2 transition-all shadow-lg shadow-purple-500/20"
            >
              📊 策略对比
            </Link>
            
            {/* 用户信息 */}
            <UserProfile 
              user={user} 
              onLoginClick={() => setShowLoginModal(true)}
              onLogout={logout}
            />
          </div>
        </div>
      </header>

      {/* 主内容区 */}
      <main className="p-4">
        <div className="flex gap-4">
          {/* 左侧面板 - 控制和统计 */}
          <div className="w-80 shrink-0 space-y-4">
            <ControlPanel
              config={state.config}
              status={state.status}
              onStart={handleStart}
              onPause={handlePause}
              onStop={handleStop}
              onReset={handleReset}
              onOfflineReplay={handleOfflineReplay}
              onSpeedChange={handleSpeedChange}
              onStrategyChange={handleStrategyChange}
              onScaleChange={handleScaleChange}
              onCollaborationChange={handleCollaborationChange}
            />
            <StatisticsPanel
              statistics={state.statistics}
              events={state.eventLog}
              currentTime={state.currentTime}
              maxTime={state.config.maxSimulationTime}
            />
          </div>

          {/* 中间 - 地图 */}
          <div className="flex-1">
            <div className="w-full h-[600px] relative rounded-xl overflow-hidden border border-gray-800 bg-gray-900/50 shadow-2xl backdrop-blur-sm">
              <AMapRealtimeMap
                state={state}
                onNodeClick={handleNodeClick}
                selectedVehicleId={selectedVehicleId}
              />
            </div>
            
            {/* 快速信息条 */}
            <div className="mt-4 grid grid-cols-5 gap-3">
              <div className="bg-gray-900/80 rounded-lg p-3 border border-gray-700 stat-shine">
                <div className="text-xs text-gray-500 mb-1">🚚 车辆数</div>
                <div className="text-xl font-bold text-white">{state.vehicles.length}</div>
                <div className="text-[10px] text-gray-600 mt-1">
                  运行中: {state.vehicles.filter(v => v.status === 'delivering').length}
                </div>
              </div>
              <div className="bg-gray-900/80 rounded-lg p-3 border border-yellow-700/50 stat-shine">
                <div className="text-xs text-gray-500 mb-1">📦 待处理</div>
                <div className="text-xl font-bold text-yellow-400">{state.statistics.pendingTasks}</div>
                <div className="text-[10px] text-gray-600 mt-1">
                  进行中: {state.tasks.filter(t => t.status === 'in_progress').length}
                </div>
              </div>
              <div className="bg-gray-900/80 rounded-lg p-3 border border-green-700/50 stat-shine">
                <div className="text-xs text-gray-500 mb-1">✅ 已完成</div>
                <div className="text-xl font-bold text-green-400 animate-countUp">{state.statistics.completedTasks}</div>
                <div className="text-[10px] text-gray-600 mt-1">
                  失败: <span className="text-red-400">{state.statistics.failedTasks}</span>
                </div>
              </div>
              <div className="bg-gray-900/80 rounded-lg p-3 border border-orange-700/50 relative overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-r from-orange-500/5 to-yellow-500/5"></div>
                <div className="relative">
                  <div className="text-xs text-gray-500 mb-1">💰 总收益</div>
                  <div className="text-xl font-bold text-orange-400">{state.statistics.totalScore.toFixed(0)}</div>
                  <div className="text-[10px] text-gray-600 mt-1">
                    效率: {state.statistics.completedTasks > 0 ? (state.statistics.totalScore / state.statistics.completedTasks).toFixed(1) : '--'}/单
                  </div>
                </div>
              </div>
              <div className="bg-gray-900/80 rounded-lg p-3 border border-blue-700/50">
                <div className="text-xs text-gray-500 mb-1">⏱️ 运行时间</div>
                <div className="text-xl font-bold text-blue-400">
                  {Math.floor(state.currentTime / 60)}:{(state.currentTime % 60).toFixed(0).padStart(2, '0')}
                </div>
                <div className="w-full h-1 bg-gray-800 rounded-full mt-2 overflow-hidden">
                  <div 
                    className="h-full bg-gradient-to-r from-blue-500 to-cyan-500 transition-all duration-300"
                    style={{ width: `${(state.currentTime / state.config.maxSimulationTime) * 100}%` }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* 右侧面板 - 车辆/任务/充电站 */}
          <div className="w-96 shrink-0">
            {/* 标签切换 */}
            <div className="flex gap-1 mb-3 bg-gray-900 p-1 rounded-lg">
              <button
                onClick={() => setActiveTab('vehicles')}
                className={`flex-1 py-2 px-3 text-sm rounded-md transition-colors ${
                  activeTab === 'vehicles'
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800'
                }`}
              >
                🚚 车队 ({state.vehicles.length})
              </button>
              <button
                onClick={() => setActiveTab('tasks')}
                className={`flex-1 py-2 px-3 text-sm rounded-md transition-colors ${
                  activeTab === 'tasks'
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800'
                }`}
              >
                📦 任务 ({state.tasks.length})
              </button>
              <button
                onClick={() => setActiveTab('stations')}
                className={`flex-1 py-2 px-3 text-sm rounded-md transition-colors ${
                  activeTab === 'stations'
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800'
                }`}
              >
                ⚡ 充电站 ({state.chargingStations.length})
              </button>
            </div>

            {/* 面板内容 */}
            {activeTab === 'vehicles' && (
              <VehiclePanel
                vehicles={state.vehicles}
                selectedVehicleId={selectedVehicleId}
                onSelectVehicle={setSelectedVehicleId}
              />
            )}
            {activeTab === 'tasks' && (
              <TaskPanel
                tasks={state.tasks}
                currentTime={state.currentTime}
              />
            )}
            {activeTab === 'stations' && (
              <ChargingStationPanel
                stations={state.chargingStations}
                vehicles={state.vehicles}
              />
            )}
          </div>
        </div>
      </main>

      {/* 底部信息栏 */}
      <footer className="fixed bottom-0 left-0 right-0 bg-gray-900/90 backdrop-blur border-t border-gray-800 px-6 py-2">
        <div className="flex items-center justify-between text-xs text-gray-500">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
              系统运行中
            </span>
            <span>|</span>
            <span>数据结构课程大作业</span>
            <span>|</span>
            <span className="text-blue-400">新能源物流车队协同调度</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded">Dijkstra</span>
            <span className="px-2 py-0.5 bg-green-500/20 text-green-400 rounded">A*</span>
            <span>调度策略: 6种</span>
            <span>|</span>
            <span>问题规模: 4种</span>
          </div>
        </div>
      </footer>

      {/* 登录模态框 */}
      <LoginModal
        isOpen={showLoginModal}
        onClose={() => setShowLoginModal(false)}
        onLogin={login}
      />

      {/* 排行榜模态框 */}
      {showLeaderboard && (
        <LeaderboardPanel
          currentUserId={user?.id}
          onClose={() => setShowLeaderboard(false)}
          isModal={true}
        />
      )}

      {/* 离线回放模态框 */}
      {showOfflineModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-[100]">
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-[600px] shadow-2xl">
            <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
              <span>🧠</span> 离线求解日志回放
            </h2>
            <p className="text-gray-400 text-sm mb-4">
              请将算法离线求解得出的状态日志 (JSON格式的数组) 粘贴到下方，系统将自动高帧率进行展示，不再穿墙。
            </p>
            <textarea
              className="w-full h-64 bg-gray-950 border border-gray-700 rounded-lg p-3 text-gray-300 font-mono text-sm focus:outline-none focus:border-blue-500 transition-colors mb-4"
              placeholder='[ { "status": "running", "currentTime": 0, "vehicles": [...], ... }, ... ]'
              value={offlineLogText}
              onChange={(e) => setOfflineLogText(e.target.value)}
            />
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowOfflineModal(false)}
                className="px-4 py-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handlePlayOffline}
                className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-700 text-white font-medium transition-colors"
              >
                开始回放
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
