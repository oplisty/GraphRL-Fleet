import re

filepath = '/Users/xueyuxuan/大二下/大二/data structure/Data-Structure-HW/Engine/Framework/api/server.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

old_pos = """        node = env.graph.nodes[vehicle.current_node]
        assigned_tasks = []"""

new_pos = """        node = env.graph.nodes[vehicle.current_node]
        x, y = node.x, node.y
        if vehicle.route_index < len(vehicle.route) - 1:
            u = vehicle.route[vehicle.route_index]
            v = vehicle.route[vehicle.route_index + 1]
            u_node = env.graph.nodes[u]
            v_node = env.graph.nodes[v]
            edge_dist = env.graph.edge_distance(u, v) or 1e-9
            progress = 1.0 - (vehicle.distance_to_next / edge_dist)
            progress = max(0.0, min(1.0, progress))
            x = u_node.x + (v_node.x - u_node.x) * progress
            y = u_node.y + (v_node.y - u_node.y) * progress

        assigned_tasks = []"""

if new_pos not in content:
    content = content.replace(old_pos, new_pos)

old_dict_pos = """                "position": {"x": node.x, "y": node.y},"""
new_dict_pos = """                "position": {"x": x, "y": y},"""

if new_dict_pos not in content:
    content = content.replace(old_dict_pos, new_dict_pos)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
