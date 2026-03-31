import re

filepath = '/Users/xueyuxuan/大二下/大二/data structure/Data-Structure-HW/UI/logistics-ui/app/components/AMapRealtimeMap.tsx'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

if "wgs84togcj02" not in content:
    content = content.replace("import { SimulationState } from '../types';", 
                              "import { SimulationState } from '../types';\nimport { wgs84togcj02 } from '../utils/geo';")
    
    old_proj = """  if (isLikelyLngLat(minX, maxX, minY, maxY)) {
    const toLngLat = (x: number, y: number): LngLat => [x, y];"""
    new_proj = """  if (isLikelyLngLat(minX, maxX, minY, maxY)) {
    const toLngLat = (x: number, y: number): LngLat => wgs84togcj02(x, y);"""
    content = content.replace(old_proj, new_proj)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
