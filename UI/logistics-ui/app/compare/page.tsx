'use client';

import React, { useState, useCallback } from 'react';
import { SchedulingStrategy, Statistics } from '../types';
import { SimulationEngine, ProblemScales } from '../core/simulation';
import Link from 'next/link';

// 策略配置
const strategies: { id: SchedulingStrategy; name: string; description: string; icon: string }[] = [
  { id: 'nearest_first', name: '最近优先', description: '优先处理路径最近且可执行的任务', icon: '📍' },
  { id: 'largest_first', name: '最大优先', description: '优先处理货物最重的任务', icon: '📦' },
  { id: 'earliest_deadline', name: '截止优先（EDF）', description: '优先处理截止时间最早的任务', icon: '⏰' },
  { id: 'q_learning', name: 'Q-learning', description: '用训练好的 Q-learning 模型选择启发式规则', icon: '🧠' },
];

// 策略比较结果
interface CompareResult {
  strategy: SchedulingStrategy;
  statistics: Statistics;
  runTime: number;
}

export default function ComparePage() {
  const [selectedStrategies, setSelectedStrategies] = useState<SchedulingStrategy[]>(['nearest_first', 'largest_first', 'earliest_deadline']);
  const [selectedScale, setSelectedScale] = useState(ProblemScales[1]);
  const [isRunning, setIsRunning] = useState(false);
  const [results, setResults] = useState<CompareResult[]>([]);
  const [progress, setProgress] = useState(0);
  const [currentStrategy, setCurrentStrategy] = useState<SchedulingStrategy | null>(null);

  // 运行对比测试
  const runComparison = useCallback(async () => {
    if (selectedStrategies.length === 0) return;

    setIsRunning(true);
    setResults([]);
    setProgress(0);

    const newResults: CompareResult[] = [];
    const totalStrategies = selectedStrategies.length;

    for (let i = 0; i < selectedStrategies.length; i++) {
      const strategy = selectedStrategies[i];
      setCurrentStrategy(strategy);

      // 创建新的引擎实例
      const engine = new SimulationEngine();
      engine.initialize({
        scale: selectedScale,
        strategy,
        simulationSpeed: 100, // 快速模拟
        maxSimulationTime: 240, // 4小时模拟
        enableCollaboration: strategy === 'collaborative'
      });

      // 运行模拟
      const startTime = Date.now();
      
      // 使用Promise来等待模拟完成
      await new Promise<void>((resolve) => {
        engine.setOnStateChange((state) => {
          if (state.status === 'completed') {
            const endTime = Date.now();
            newResults.push({
              strategy,
              statistics: { ...state.statistics },
              runTime: endTime - startTime
            });
            setResults([...newResults]);
            resolve();
          }
        });
        engine.start();
      });

      setProgress(((i + 1) / totalStrategies) * 100);
    }

    setCurrentStrategy(null);
    setIsRunning(false);
  }, [selectedStrategies, selectedScale]);

  // 切换策略选择
  const toggleStrategy = (strategy: SchedulingStrategy) => {
    if (selectedStrategies.includes(strategy)) {
      setSelectedStrategies(selectedStrategies.filter(s => s !== strategy));
    } else {
      setSelectedStrategies([...selectedStrategies, strategy]);
    }
  };

  // 获取最佳结果
  const getBestResult = (metric: keyof Statistics) => {
    if (results.length === 0) return null;
    
    let bestIdx = 0;
    for (let i = 1; i < results.length; i++) {
      const currentValue = results[i].statistics[metric] as number;
      const bestValue = results[bestIdx].statistics[metric] as number;
      
      // 对于失败任务数，越小越好
      if (metric === 'failedTasks') {
        if (currentValue < bestValue) bestIdx = i;
      } else {
        if (currentValue > bestValue) bestIdx = i;
      }
    }
    return results[bestIdx].strategy;
  };

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6">
      <div className="max-w-6xl mx-auto">
        {/* 头部 */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold mb-2">📊 调度策略对比分析</h1>
            <p className="text-gray-400">比较不同调度策略在相同问题规模下的表现</p>
          </div>
          <Link
            href="/"
            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm flex items-center gap-2"
          >
            ← 返回主界面
          </Link>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 配置面板 */}
          <div className="bg-gray-900 rounded-lg border border-gray-700 p-6">
            <h2 className="text-lg font-semibold mb-4">⚙️ 测试配置</h2>

            {/* 问题规模选择 */}
            <div className="mb-6">
              <label className="block text-sm text-gray-400 mb-2">问题规模</label>
              <select
                value={selectedScale.id}
                onChange={(e) => {
                  const scale = ProblemScales.find(s => s.id === e.target.value);
                  if (scale) setSelectedScale(scale);
                }}
                disabled={isRunning}
                className="w-full py-2 px-3 bg-gray-700 text-white rounded-lg border border-gray-600"
              >
                {ProblemScales.map(scale => (
                  <option key={scale.id} value={scale.id}>
                    {scale.name} - {scale.description}
                  </option>
                ))}
              </select>
            </div>

            {/* 策略选择 */}
            <div className="mb-6">
              <label className="block text-sm text-gray-400 mb-2">选择要对比的策略</label>
              <div className="space-y-2">
                {strategies.map(strategy => (
                  <button
                    key={strategy.id}
                    onClick={() => toggleStrategy(strategy.id)}
                    disabled={isRunning}
                    className={`w-full p-3 rounded-lg text-left flex items-center gap-3 transition-colors ${
                      selectedStrategies.includes(strategy.id)
                        ? 'bg-blue-600 ring-2 ring-blue-400'
                        : 'bg-gray-700 hover:bg-gray-600'
                    } disabled:opacity-50`}
                  >
                    <span className="text-xl">{strategy.icon}</span>
                    <div>
                      <div className="font-medium">{strategy.name}</div>
                      <div className="text-xs text-gray-300">{strategy.description}</div>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* 开始按钮 */}
            <button
              onClick={runComparison}
              disabled={isRunning || selectedStrategies.length === 0}
              className="w-full py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg font-medium flex items-center justify-center gap-2"
            >
              {isRunning ? (
                <>
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  测试中... {progress.toFixed(0)}%
                </>
              ) : (
                <>
                  <span>▶</span>
                  开始对比测试
                </>
              )}
            </button>

            {currentStrategy && (
              <div className="mt-4 text-center text-sm text-gray-400">
                正在测试: {strategies.find(s => s.id === currentStrategy)?.name}
              </div>
            )}
          </div>

          {/* 结果展示 */}
          <div className="lg:col-span-2 space-y-6">
            {results.length === 0 ? (
              <div className="bg-gray-900 rounded-lg border border-gray-700 p-12 text-center">
                <div className="text-6xl mb-4">📈</div>
                <h3 className="text-xl font-semibold text-gray-400 mb-2">暂无测试结果</h3>
                <p className="text-gray-500">选择要对比的策略，然后点击&ldquo;开始对比测试&rdquo;</p>
              </div>
            ) : (
              <>
                {/* 结果卡片 */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {results.map((result) => {
                    const strategy = strategies.find(s => s.id === result.strategy)!;
                    const isTopScore = getBestResult('totalScore') === result.strategy;
                    const isTopCompletion = getBestResult('completedTasks') === result.strategy;
                    const isLowestFailure = getBestResult('failedTasks') === result.strategy;

                    return (
                      <div
                        key={result.strategy}
                        className={`bg-gray-900 rounded-lg border p-4 ${
                          isTopScore ? 'border-yellow-500 ring-1 ring-yellow-500' : 'border-gray-700'
                        }`}
                      >
                        <div className="flex items-center gap-3 mb-4">
                          <span className="text-2xl">{strategy.icon}</span>
                          <div>
                            <div className="font-medium">{strategy.name}</div>
                            {isTopScore && (
                              <span className="text-xs bg-yellow-500 text-black px-2 py-0.5 rounded">
                                🏆 最高得分
                              </span>
                            )}
                          </div>
                        </div>

                        <div className="space-y-2 text-sm">
                          <div className="flex justify-between">
                            <span className="text-gray-400">总得分</span>
                            <span className={`font-bold ${isTopScore ? 'text-yellow-400' : 'text-white'}`}>
                              {result.statistics.totalScore.toFixed(0)}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-400">完成任务</span>
                            <span className={isTopCompletion ? 'text-green-400' : ''}>
                              {result.statistics.completedTasks}/{result.statistics.totalTasks}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-400">失败任务</span>
                            <span className={isLowestFailure ? 'text-green-400' : 'text-red-400'}>
                              {result.statistics.failedTasks}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-400">准时率</span>
                            <span>{result.statistics.onTimeRate.toFixed(1)}%</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-400">平均配送时间</span>
                            <span>{result.statistics.averageDeliveryTime.toFixed(1)}分钟</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-400">总行驶距离</span>
                            <span>{result.statistics.totalDistance.toFixed(1)} km</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-400">车辆利用率</span>
                            <span>{result.statistics.vehicleUtilization.toFixed(1)}%</span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* 柱状图对比 */}
                {results.length > 1 && (
                  <div className="bg-gray-900 rounded-lg border border-gray-700 p-6">
                    <h3 className="text-lg font-semibold mb-4">📊 得分对比</h3>
                    <div className="space-y-3">
                      {results.map(result => {
                        const strategy = strategies.find(s => s.id === result.strategy)!;
                        const maxScore = Math.max(...results.map(r => r.statistics.totalScore));
                        const widthPercent = (result.statistics.totalScore / maxScore) * 100;

                        return (
                          <div key={result.strategy}>
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-sm flex items-center gap-2">
                                <span>{strategy.icon}</span>
                                {strategy.name}
                              </span>
                              <span className="text-sm font-medium">{result.statistics.totalScore.toFixed(0)}</span>
                            </div>
                            <div className="h-6 bg-gray-700 rounded overflow-hidden">
                              <div
                                className="h-full bg-gradient-to-r from-blue-500 to-cyan-500 transition-all"
                                style={{ width: `${widthPercent}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* 分析总结 */}
                {results.length > 1 && (
                  <div className="bg-gray-900 rounded-lg border border-gray-700 p-6">
                    <h3 className="text-lg font-semibold mb-4">💡 分析总结</h3>
                    <div className="space-y-3 text-sm text-gray-300">
                      <p>
                        在 <span className="text-white font-medium">{selectedScale.name}</span> 问题规模下，
                        <span className="text-yellow-400 font-medium">
                          {strategies.find(s => s.id === getBestResult('totalScore'))?.name}
                        </span> 策略获得了最高得分。
                      </p>
                      <p>
                        <span className="text-green-400 font-medium">
                          {strategies.find(s => s.id === getBestResult('completedTasks'))?.name}
                        </span> 策略完成了最多的任务，
                        而 <span className="text-green-400 font-medium">
                          {strategies.find(s => s.id === getBestResult('failedTasks'))?.name}
                        </span> 策略的失败任务数最少。
                      </p>
                      <p className="text-gray-400 italic">
                        提示：不同的策略适用于不同的场景，请根据实际需求选择合适的调度策略。
                      </p>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
