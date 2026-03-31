import re

filepath = '/Users/xueyuxuan/大二下/大二/data structure/Data-Structure-HW/UI/logistics-ui/app/components/AMapRealtimeMap.tsx'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix straight line: previously, vehicle rendering uses route logic, but we should make sure we ONLY draw the "route" paths, not lines directly to nodes.
# Let's inspect the AMapRealtimeMap.tsx
