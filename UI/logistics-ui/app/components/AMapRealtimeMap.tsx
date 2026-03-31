'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { SimulationState } from '../types';
import { wgs84togcj02 } from '../utils/geo';

interface AMapRealtimeMapProps {
  state: SimulationState;
  width?: number;
  height?: number;
  onNodeClick?: (nodeId: string) => void;
  selectedVehicleId?: string;
}

type LngLat = [number, number];

interface AMapOverlay {
  setMap: (map: AMapInstance | null) => void;
}

interface AMapEventOverlay extends AMapOverlay {
  on?: (event: string, handler: () => void) => void;
}

interface AMapInstance {
  addControl: (control: unknown) => void;
  add: (overlays: unknown[]) => void;
  setLimitBounds?: (bounds: unknown) => void;
  setFitView: (
    overlays: unknown[],
    immediately?: boolean,
    avoid?: number[],
    maxZoom?: number
  ) => void;
  destroy: () => void;
}

interface AMapNamespace {
  Map: new (container: HTMLElement, options: Record<string, unknown>) => AMapInstance;
  Bounds?: new (southWest: LngLat, northEast: LngLat) => unknown;
  Scale: new () => unknown;
  ToolBar: new (options?: Record<string, unknown>) => unknown;
  Polyline: new (options: Record<string, unknown>) => AMapOverlay;
  CircleMarker: new (options: Record<string, unknown>) => AMapEventOverlay;
  Text: new (options: Record<string, unknown>) => AMapOverlay;
  Pixel: new (x: number, y: number) => unknown;
}

interface AMapWindow extends Window {
  AMap?: AMapNamespace;
  _AMapSecurityConfig?: { securityJsCode: string };
}

const DEFAULT_CENTER: LngLat = [113.2644, 23.1291]; // 广州
const DEFAULT_SPAN_DEGREE = 0.2;
const DEFAULT_MAX_ROAD_SEGMENTS = 12000;
const DEFAULT_MAX_NODE_MARKERS = 8000;
const DEFAULT_SHOW_ROAD_SEGMENTS = false;
const DEFAULT_SHOW_ROAD_NODE_MARKERS = false;

let amapScriptPromise: Promise<void> | null = null;

function loadAMapScript(apiKey: string, securityCode?: string): Promise<void> {
  if (typeof window === 'undefined') {
    return Promise.reject(new Error('AMap can only be used in browser'));
  }

  const win = window as AMapWindow;
  if (win.AMap) {
    return Promise.resolve();
  }

  if (amapScriptPromise) {
    return amapScriptPromise;
  }

  amapScriptPromise = new Promise((resolve, reject) => {
    if (securityCode) {
      win._AMapSecurityConfig = { securityJsCode: securityCode };
    }

    const script = document.createElement('script');
    script.id = 'amap-jsapi-loader';
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(apiKey)}&plugin=AMap.Scale,AMap.ToolBar`;
    script.async = true;

    script.onload = () => resolve();
    script.onerror = () => reject(new Error('Failed to load AMap JS API'));

    document.head.appendChild(script);
  });

  return amapScriptPromise;
}

function clampNumber(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function parseBooleanEnv(value: string | undefined, fallback: boolean): boolean {
  if (!value) return fallback;
  const text = value.trim().toLowerCase();
  if (text === '1' || text === 'true' || text === 'yes' || text === 'on') return true;
  if (text === '0' || text === 'false' || text === 'no' || text === 'off') return false;
  return fallback;
}

function isLikelyLngLat(minX: number, maxX: number, minY: number, maxY: number): boolean {
  const lonValid = minX >= 70 && maxX <= 140;
  const latValid = minY >= 0 && maxY <= 60;
  const rangeValid = maxX - minX <= 5 && maxY - minY <= 5;
  return lonValid && latValid && rangeValid;
}

function buildProjection(state: SimulationState, center: LngLat, spanDegree: number) {
  const nodes = Array.from(state.graph.nodes.values());

  if (nodes.length === 0) {
    return {
      toLngLat: (x: number, y: number): LngLat => [center[0] + x * 0.001, center[1] + y * 0.001],
      bboxPoints: [center],
    };
  }

  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;

  for (const node of nodes) {
    minX = Math.min(minX, node.position.x);
    maxX = Math.max(maxX, node.position.x);
    minY = Math.min(minY, node.position.y);
    maxY = Math.max(maxY, node.position.y);
  }

  if (isLikelyLngLat(minX, maxX, minY, maxY)) {
    const toLngLat = (x: number, y: number): LngLat => wgs84togcj02(x, y);
    const bboxPoints: LngLat[] = [
      [minX, minY],
      [minX, maxY],
      [maxX, minY],
      [maxX, maxY],
    ];
    return { toLngLat, bboxPoints };
  }

  const midX = (minX + maxX) / 2;
  const midY = (minY + maxY) / 2;

  const rangeX = Math.max(1, maxX - minX);
  const rangeY = Math.max(1, maxY - minY);
  const range = Math.max(rangeX, rangeY);
  const scale = spanDegree / range;

  const toLngLat = (x: number, y: number): LngLat => {
    const lng = center[0] + (x - midX) * scale;
    // 地图纬度向上增大，这里反转 y 轴保持视觉直觉一致
    const lat = center[1] + (midY - y) * scale;
    return [lng, lat];
  };

  const bboxPoints: LngLat[] = [
    toLngLat(minX, minY),
    toLngLat(minX, maxY),
    toLngLat(maxX, minY),
    toLngLat(maxX, maxY),
  ];

  return { toLngLat, bboxPoints };
}

const AMapRealtimeMap: React.FC<AMapRealtimeMapProps> = ({
  state,
  width = 800,
  height = 600,
  onNodeClick,
  selectedVehicleId,
}) => {
  const apiKey = process.env.NEXT_PUBLIC_AMAP_KEY || '';
  const securityCode = process.env.NEXT_PUBLIC_AMAP_SECURITY_CODE || '';

  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<AMapInstance | null>(null);
  const overlaysRef = useRef<AMapOverlay[]>([]);
  const hasFitViewRef = useRef(false);

  const [loadStatus, setLoadStatus] = useState<'loading' | 'ready' | 'error'>(
    apiKey ? 'loading' : 'error'
  );

  const center = useMemo<LngLat>(() => {
    const lng = Number(process.env.NEXT_PUBLIC_MAP_CENTER_LNG ?? DEFAULT_CENTER[0]);
    const lat = Number(process.env.NEXT_PUBLIC_MAP_CENTER_LAT ?? DEFAULT_CENTER[1]);

    if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
      return DEFAULT_CENTER;
    }

    return [clampNumber(lng, -180, 180), clampNumber(lat, -90, 90)];
  }, []);

  const spanDegree = useMemo(() => {
    const value = Number(process.env.NEXT_PUBLIC_MAP_SPAN_DEGREE ?? DEFAULT_SPAN_DEGREE);
    if (!Number.isFinite(value) || value <= 0) return DEFAULT_SPAN_DEGREE;
    return clampNumber(value, 0.01, 2);
  }, []);

  const maxRoadSegments = useMemo(() => {
    const value = Number(process.env.NEXT_PUBLIC_MAX_ROAD_SEGMENTS ?? DEFAULT_MAX_ROAD_SEGMENTS);
    if (!Number.isFinite(value) || value < 1000) return DEFAULT_MAX_ROAD_SEGMENTS;
    return Math.floor(value);
  }, []);

  const maxNodeMarkers = useMemo(() => {
    const value = Number(process.env.NEXT_PUBLIC_MAX_NODE_MARKERS ?? DEFAULT_MAX_NODE_MARKERS);
    if (!Number.isFinite(value) || value < 1000) return DEFAULT_MAX_NODE_MARKERS;
    return Math.floor(value);
  }, []);

  const showRoadSegments = useMemo(
    () => parseBooleanEnv(process.env.NEXT_PUBLIC_SHOW_ROAD_SEGMENTS, DEFAULT_SHOW_ROAD_SEGMENTS),
    []
  );

  const showRoadNodeMarkers = useMemo(
    () => parseBooleanEnv(process.env.NEXT_PUBLIC_SHOW_ROAD_NODE_MARKERS, DEFAULT_SHOW_ROAD_NODE_MARKERS),
    []
  );

  useEffect(() => {
    if (!apiKey) {
      return;
    }

    let disposed = false;

    loadAMapScript(apiKey, securityCode)
      .then(() => {
        if (disposed) return;
        setLoadStatus('ready');
      })
      .catch((error) => {
        console.error('AMap load failed:', error);
        if (!disposed) {
          setLoadStatus('error');
        }
      });

    return () => {
      disposed = true;
    };
  }, [apiKey, securityCode]);

  useEffect(() => {
    if (loadStatus !== 'ready') return;
    if (!containerRef.current) return;
    if (mapRef.current) return;

    const AMap = (window as AMapWindow).AMap;
    if (!AMap) return;

    const map = new AMap.Map(containerRef.current, {
      center,
      zoom: 12,
      viewMode: '2D',
      resizeEnable: true,
      mapStyle: 'amap://styles/normal',
    });

    map.addControl(new AMap.Scale());
    map.addControl(new AMap.ToolBar({ position: 'RB' }));

    mapRef.current = map;

    return () => {
      overlaysRef.current.forEach((overlay) => {
        if (overlay?.setMap) {
          overlay.setMap(null);
        }
      });
      overlaysRef.current = [];
      hasFitViewRef.current = false;

      if (mapRef.current) {
        mapRef.current.destroy();
        mapRef.current = null;
      }
    };
  }, [loadStatus, center]);

  useEffect(() => {
    const map = mapRef.current;
    const AMap = (window as AMapWindow).AMap;
    if (!map || !AMap) return;

    overlaysRef.current.forEach((overlay) => {
      if (overlay?.setMap) {
        overlay.setMap(null);
      }
    });
    overlaysRef.current = [];

    const projection = buildProjection(state, center, spanDegree);
    const overlays: AMapOverlay[] = [];

    // 道路
    if (showRoadSegments) {
      const allEdges = Array.from(state.graph.edges.values()).flat();
      const edgeStep = Math.max(1, Math.ceil(allEdges.length / maxRoadSegments));
      const edgeDedup = new Set<string>();

      for (let edgeIndex = 0; edgeIndex < allEdges.length; edgeIndex += edgeStep) {
        const edge = allEdges[edgeIndex];
        const edgeKey = [edge.from, edge.to].sort().join('-');
        if (edgeDedup.has(edgeKey)) continue;
        edgeDedup.add(edgeKey);

        const fromNode = state.graph.nodes.get(edge.from);
        const toNode = state.graph.nodes.get(edge.to);
        if (!fromNode || !toNode) continue;

        const line = new AMap.Polyline({
          path: [
            projection.toLngLat(fromNode.position.x, fromNode.position.y),
            projection.toLngLat(toNode.position.x, toNode.position.y),
          ],
          strokeColor: edge.trafficFactor > 1.1 ? '#ef4444' : '#64748b',
          strokeWeight: edge.trafficFactor > 1.1 ? 4 : 2,
          strokeStyle: edge.trafficFactor > 1.1 ? 'dashed' : 'solid',
          strokeOpacity: 0.9,
        });

        line.setMap(map);
        overlays.push(line);
      }
    }

    // 节点
    const allNodes = Array.from(state.graph.nodes.values());
    const nodeStep = Math.max(1, Math.ceil(allNodes.length / maxNodeMarkers));

    for (let nodeIndex = 0; nodeIndex < allNodes.length; nodeIndex += nodeStep) {
      const node = allNodes[nodeIndex];

      // Hide dense road-node dots by default to keep vehicles and tasks visible.
      if (!showRoadNodeMarkers && node.type !== 'warehouse' && node.type !== 'charging_station') {
        continue;
      }

      const centerPoint = projection.toLngLat(node.position.x, node.position.y);

      let color = '#6b7280';
      let radius = 4;
      if (node.type === 'warehouse') {
        color = '#3b82f6';
        radius = 8;
      } else if (node.type === 'charging_station') {
        color = '#10b981';
        radius = 7;
      }

      const marker = new AMap.CircleMarker({
        center: centerPoint,
        radius,
        fillColor: color,
        fillOpacity: 0.95,
        strokeColor: '#0f172a',
        strokeWeight: 1,
        bubble: true,
      });

      marker.setMap(map);
      if (onNodeClick && marker.on) {
        marker.on('click', () => onNodeClick(node.id));
      }
      overlays.push(marker);
    }

    // 任务
    const activeTasks = state.tasks.filter((task) =>
      task.status === 'pending' || task.status === 'assigned' || task.status === 'in_progress'
    );

    for (const task of activeTasks) {
      const point = projection.toLngLat(task.position.x, task.position.y);
      const isPending = task.status === 'pending';

      let color = '#6b7280';
      if (task.priority === 'urgent') color = '#ef4444';
      else if (task.priority === 'high') color = '#f59e0b';
      else if (task.priority === 'medium') color = '#3b82f6';
      else if (task.priority === 'low') color = '#10b981';

      const marker = new AMap.CircleMarker({
        center: point,
        radius: 6,
        fillColor: color,
        fillOpacity: isPending ? 0.95 : 0.45,
        strokeColor: '#111827',
        strokeWeight: 1,
      });
      marker.setMap(map);
      overlays.push(marker);
    }

    // 车辆 + 车辆路径
    for (const vehicle of state.vehicles) {
      const vehiclePoint = projection.toLngLat(vehicle.position.x, vehicle.position.y);

      if (vehicle.path.length > 0 && (vehicle.status === 'delivering' || vehicle.status === 'returning')) {
        const pathPoints: LngLat[] = [vehiclePoint];
        for (const nodeId of vehicle.path) {
          const node = state.graph.nodes.get(nodeId);
          if (node) {
            pathPoints.push(projection.toLngLat(node.position.x, node.position.y));
          }
        }

        const route = new AMap.Polyline({
          path: pathPoints,
          strokeColor: vehicle.color,
          strokeWeight: 3,
          strokeOpacity: 0.45,
          strokeStyle: 'dashed',
        });

        route.setMap(map);
        overlays.push(route);
      }

      const vehicleMarker = new AMap.CircleMarker({
        center: vehiclePoint,
        radius: selectedVehicleId === vehicle.id ? 14 : 10,
        fillColor: vehicle.color,
        fillOpacity: 0.95,
        strokeColor: selectedVehicleId === vehicle.id ? '#f59e0b' : '#ffffff',
        strokeWeight: selectedVehicleId === vehicle.id ? 3 : 2,
        zIndex: 120,
      });

      vehicleMarker.setMap(map);
      overlays.push(vehicleMarker);

      const label = new AMap.Text({
        text: vehicle.name,
        position: vehiclePoint,
        offset: new AMap.Pixel(0, -18),
        style: {
          color: '#0f172a',
          fontSize: '11px',
          fontWeight: '700',
          padding: '1px 4px',
          backgroundColor: '#ffffffcc',
          border: '1px solid #94a3b8',
          borderRadius: '8px',
        },
      });

      label.setMap(map);
      overlays.push(label);
    }

    overlaysRef.current = overlays;

    if (!hasFitViewRef.current && projection.bboxPoints.length > 1) {
      const boundsMask = projection.bboxPoints.map((point): AMapOverlay =>
        new AMap.CircleMarker({ center: point, radius: 0.1, fillOpacity: 0, strokeOpacity: 0 })
      );
      map.add(boundsMask);
      map.setFitView(boundsMask, false, [60, 60, 60, 60], 14);

      if (AMap.Bounds && map.setLimitBounds) {
        const lngList = projection.bboxPoints.map((p) => p[0]);
        const latList = projection.bboxPoints.map((p) => p[1]);
        const minLng = Math.min(...lngList);
        const maxLng = Math.max(...lngList);
        const minLat = Math.min(...latList);
        const maxLat = Math.max(...latList);
        map.setLimitBounds(new AMap.Bounds([minLng, minLat], [maxLng, maxLat]));
      }

      boundsMask.forEach((b) => b.setMap(null));
      hasFitViewRef.current = true;
    }
  }, [
    state,
    center,
    spanDegree,
    maxRoadSegments,
    maxNodeMarkers,
    showRoadSegments,
    showRoadNodeMarkers,
    selectedVehicleId,
    onNodeClick,
  ]);

  if (loadStatus === 'error') {
    return (
      <div
        className="rounded-lg border border-red-800/60 bg-red-950/40 p-4 text-sm text-red-200"
        style={{ width, height }}
      >
        未能加载高德地图。请在 UI 目录配置 .env.local 并提供 NEXT_PUBLIC_AMAP_KEY。
      </div>
    );
  }

  return (
    <div className="relative rounded-lg overflow-hidden border border-gray-700" style={{ width, height }}>
      {loadStatus === 'loading' && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-gray-900/60 text-sm text-gray-200 backdrop-blur-sm">
          正在加载高德地图...
        </div>
      )}
      <div ref={containerRef} className="h-full w-full" />
      <div className="pointer-events-none absolute left-3 top-3 z-20 rounded-md bg-gray-900/80 px-3 py-2 text-xs text-gray-100">
        实时地图模式（高德底图 + 仿真叠加）
      </div>
      <div className="pointer-events-none absolute right-3 top-3 z-20 rounded-md bg-gray-900/80 px-3 py-2 text-xs text-gray-100">
        已抽稀显示: 路段≤{maxRoadSegments} 节点≤{maxNodeMarkers}
        {showRoadSegments ? '（显示道路线）' : '（隐藏道路线）'}
        {showRoadNodeMarkers ? '（显示道路节点）' : '（隐藏道路节点）'}
      </div>
    </div>
  );
};

export default AMapRealtimeMap;
