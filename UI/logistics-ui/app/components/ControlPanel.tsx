'use client';

import React from 'react';
import { SimulationConfig, SchedulingStrategy, ProblemScale, SimulationStatus } from '../types';
import { ProblemScales } from '../core/simulation';

interface ControlPanelProps {
  config: SimulationConfig;
  status: SimulationStatus;
  onStart: () => void;
  onPause: () => void;
  onStop: () => void;
  onReset: () => void;
  onOfflineReplay?: () => void;
  onSpeedChange: (speed: number) => void;
  onStrategyChange: (strategy: SchedulingStrategy) => void;
  onScaleChange: (scale: ProblemScale) => void;
  onCollaborationChange: (enabled: boolean) => void;
}

// 调度策略配置
const strategies: { id: SchedulingStrategy; name: string; description: string; icon: string }[] = [
  { 
    id: 'nearest_first', 
    name: '最近优先', 
    description: '优先处理距离最近的任务',
    icon: '📍'
  },
  { 
    id: 'largest_first', 
    name: '最大优先', 
    description: '优先处理货物最重的任务',
    icon: '📦'
  },
  { 
    id: 'highest_reward', 
    name: '收益优先', 
    description: '优先处理奖励最高的任务',
    icon: '💰'
  },
  { 
    id: 'earliest_deadline', 
    name: '截止优先', 
    description: '优先处理即将超时的任务',
    icon: '⏰'
  },
  { 
    id: 'balanced', 
    name: '均衡策略', 
    description: '综合考虑多个因素',
    icon: '⚖️'
  },
  { 
    id: 'collaborative', 
    name: '协同调度', 
    description: '多车协作完成任务',
    icon: '🤝'
  },
];

// 速度选项
const speedOptions = [
  { value: 0.5, label: '0.5x' },
  { value: 1, label: '1x' },
  { value: 2, label: '2x' },
  { value: 5, label: '5x' },
  { value: 10, label: '10x' },
  { value: 20, label: '20x' },
];

const ControlPanel: React.FC<ControlPanelProps> = ({
  config,
  status,
  onStart,
  onPause,
  onStop,
  onReset,
  onOfflineReplay,
  onSpeedChange,
  onStrategyChange,
  onScaleChange,
  onCollaborationChange
}) => {
  const isRunning = status === 'running';
  const isPaused = status === 'paused';
  const isIdle = status === 'idle';

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
      <div className="bg-gray-800 px-4 py-3 border-b border-gray-700">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
          <span className="text-2xl">🎮</span>
          模拟控制
        </h3>
      </div>

      <div className="p-4 space-y-4">
        {/* 播放控制 */}
        <div className="flex items-center gap-2">
          {!isRunning ? (
            <button
              onClick={onStart}
              disabled={status === 'completed'}
              className="flex-1 py-2 px-4 bg-green-600 hover:bg-green-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg font-medium flex items-center justify-center gap-2 transition-colors"
            >
              <span>▶</span>
              {isPaused ? '继续' : '开始'}
            </button>
          ) : (
            <button
              onClick={onPause}
              className="flex-1 py-2 px-4 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg font-medium flex items-center justify-center gap-2 transition-colors"
            >
              <span>⏸</span>
              暂停
            </button>
          )}
          
          <button
            onClick={onStop}
            disabled={isIdle}
            className="py-2 px-4 bg-red-600 hover:bg-red-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg font-medium flex items-center justify-center gap-2 transition-colors"
          >
            <span>⏹</span>
            停止
          </button>
          
          <button
            onClick={onReset}
            className="py-2 px-4 bg-gray-600 hover:bg-gray-700 text-white rounded-lg font-medium flex items-center justify-center gap-2 transition-colors"
          >
            <span>🔄</span>
            重置
          </button>
        </div>

        {onOfflineReplay && (
          <button
            onClick={onOfflineReplay}
            className="w-full py-2 px-4 mt-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium flex items-center justify-center gap-2 transition-colors"
          >
            <span>🧠</span>
            离线求解并回放
          </button>
        )}

        {/* 模拟速度 */}
        <div>
          <label className="block text-sm text-gray-400 mb-2">
            模拟速度
          </label>
          <div className="flex gap-1">
            {speedOptions.map(option => (
              <button
                key={option.value}
                onClick={() => onSpeedChange(option.value)}
                className={`flex-1 py-1.5 text-sm rounded transition-colors ${
                  config.simulationSpeed === option.value
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        {/* 问题规模 */}
        <div>
          <label className="block text-sm text-gray-400 mb-2">
            问题规模
          </label>
          <select
            value={config.scale.id}
            onChange={(e) => {
              const scale = ProblemScales.find(s => s.id === e.target.value);
              if (scale) onScaleChange(scale);
            }}
            disabled={!isIdle}
            className="w-full py-2 px-3 bg-gray-700 text-white rounded-lg border border-gray-600 focus:border-blue-500 focus:outline-none disabled:opacity-50"
          >
            {ProblemScales.map(scale => (
              <option key={scale.id} value={scale.id}>
                {scale.name} - {scale.description}
              </option>
            ))}
          </select>
          {!isIdle && (
            <p className="text-xs text-gray-500 mt-1">
              需要停止模拟后才能修改规模
            </p>
          )}
        </div>

        {/* 调度策略 */}
        <div>
          <label className="block text-sm text-gray-400 mb-2">
            调度策略
          </label>
          <div className="grid grid-cols-2 gap-2">
            {strategies.map(strategy => (
              <button
                key={strategy.id}
                onClick={() => onStrategyChange(strategy.id)}
                className={`p-2 rounded-lg text-left transition-all ${
                  config.strategy === strategy.id
                    ? 'bg-blue-600 ring-2 ring-blue-400'
                    : 'bg-gray-700 hover:bg-gray-600'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="text-lg">{strategy.icon}</span>
                  <span className="text-white text-sm font-medium">{strategy.name}</span>
                </div>
                <p className="text-xs text-gray-400 mt-1 line-clamp-1">
                  {strategy.description}
                </p>
              </button>
            ))}
          </div>
        </div>

        {/* 协同调度开关 */}
        <div className="flex items-center justify-between py-2 px-3 bg-gray-800 rounded-lg">
          <div>
            <div className="text-white text-sm font-medium">多车协同</div>
            <p className="text-xs text-gray-400">允许多辆车协作完成同一任务</p>
          </div>
          <button
            onClick={() => onCollaborationChange(!config.enableCollaboration)}
            className={`relative w-12 h-6 rounded-full transition-colors ${
              config.enableCollaboration ? 'bg-blue-600' : 'bg-gray-600'
            }`}
          >
            <div
              className={`absolute top-0.5 w-5 h-5 bg-white rounded-full transition-transform ${
                config.enableCollaboration ? 'translate-x-6' : 'translate-x-0.5'
              }`}
            />
          </button>
        </div>

        {/* 状态指示 */}
        <div className="flex items-center justify-center gap-2 py-2 px-3 bg-gray-800 rounded-lg">
          <div className={`w-3 h-3 rounded-full ${
            status === 'running' ? 'bg-green-500 animate-pulse' :
            status === 'paused' ? 'bg-yellow-500' :
            status === 'completed' ? 'bg-blue-500' :
            'bg-gray-500'
          }`} />
          <span className="text-white text-sm">
            {status === 'running' ? '运行中' :
             status === 'paused' ? '已暂停' :
             status === 'completed' ? '已完成' :
             '未开始'}
          </span>
        </div>
      </div>
    </div>
  );
};

export default ControlPanel;
