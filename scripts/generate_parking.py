"""
停车场生成脚本 (Parking Generation Script)

本脚本用于解析路网文件，初始化用于存储停车位和巡航日志的数据库模式，
并生成路外(off-street)和路内(on-street)停车位及其可视化的几何表示。
"""

import math
import random
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

# ==========================================
# 1. 路径配置 (Path Configuration)
# ==========================================
BASE_DIR = Path(__file__).resolve().parent.parent
NET_FILE = BASE_DIR / "configs" / "demo.net.xml"
OUTPUT_SQL = BASE_DIR / "configs" / "schema.sql"
OUTPUT_ADD_XML = BASE_DIR / "configs" / "parking.add.xml"

# ==========================================
# 2. 路网解析 (Road Network Parsing)
# ==========================================
try:
    tree = ET.parse(NET_FILE)
    root = tree.getroot()
except FileNotFoundError:
    print(f"❌ 错误：找不到 {NET_FILE}")
    exit()

# 提取路口节点及其坐标信息
nodes = {
    n.attrib["id"]: (float(n.attrib["x"]), float(n.attrib["y"]))
    for n in root.findall("junction")
    if "x" in n.attrib
}

# 提取道路边界及其起止节点信息
edge_data = {
    e.attrib["id"]: {"from": e.attrib["from"], "to": e.attrib["to"]}
    for e in root.findall("edge")
    if "function" not in e.attrib
}
valid_edges = list(edge_data.keys())

# ==========================================
# 3. SQL与XML初始化 (SQL & XML Initialization)
# ==========================================
sql_lines = [
    "DROP TABLE IF EXISTS Parking_Spots;",
    "DROP TABLE IF EXISTS Cruising_Logs;",
    "CREATE TYPE spot_category AS ENUM ('on-street', 'off-street');",
    "CREATE TABLE Parking_Spots (spot_id VARCHAR(50) PRIMARY KEY, edge_id VARCHAR(50) NOT NULL, spot_type spot_category NOT NULL, capacity INT NOT NULL, occupied INT DEFAULT 0, base_price DECIMAL(5,2) NOT NULL, current_price DECIMAL(5,2) NOT NULL);",
    "CREATE TABLE Cruising_Logs (log_id SERIAL PRIMARY KEY, vehicle_id VARCHAR(50) NOT NULL, scenario VARCHAR(20) NOT NULL, search_time_sec FLOAT NOT NULL, cruising_distance_m FLOAT NOT NULL, final_spot_id VARCHAR(50) REFERENCES Parking_Spots(spot_id) ON DELETE CASCADE ON UPDATE CASCADE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, total_fuel_mg FLOAT NOT NULL);",
    "INSERT INTO Parking_Spots (spot_id, edge_id, spot_type, capacity, base_price, current_price) VALUES",
]

# 需要存储的 SQL 插入值列表和 XML 元素列表
insert_values = []
xml_elements = ['<?xml version="1.0" encoding="UTF-8"?>', "<additional>"]

# 随机抽取用于路外停车场的道路
off_street_edges = random.sample(valid_edges, 50)
on_street_pool = [e for e in valid_edges if e not in off_street_edges]

# ==========================================
# 4. 路外停车场生成 (Off-street Parking Generation)
# ==========================================
for i, eid in enumerate(off_street_edges):
    spot_id = f"off_street_{i}"
    capacity = 38

    insert_values.append(
        f"    ('{spot_id}', '{eid}', 'off-street', {capacity}, 8.00, 8.00)"
    )

    # --------------------------------------
    # 4.1. 几何向量计算 (Geometric Calculations)
    # --------------------------------------
    fx, fy = nodes[edge_data[eid]["from"]]
    tx, ty = nodes[edge_data[eid]["to"]]
    dx, dy = tx - fx, ty - fy
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    nx, ny = uy, -ux
    mid_x, mid_y = fx + ux * (L / 2), fy + uy * (L / 2)
    park_angle = (90 - math.degrees(math.atan2(dy, dx)) + 90) % 360

    # --------------------------------------
    # 4.2. 绘制停车场地面 (Draw Parking Area Floor)
    # --------------------------------------
    f_p = [
        (mid_x + nx * 12 - ux * 35, mid_y + ny * 12 - uy * 35),
        (mid_x + nx * 55 - ux * 35, mid_y + ny * 55 - uy * 35),
        (mid_x + nx * 55 + ux * 35, mid_y + ny * 55 + uy * 35),
        (mid_x + nx * 12 + ux * 35, mid_y + ny * 12 + uy * 35),
    ]
    shape_floor = " ".join([f"{p[0]:.2f},{p[1]:.2f}" for p in f_p])
    xml_elements.append(
        f'    <poly id="floor_{spot_id}" color="40,40,40" fill="true" layer="0" shape="{shape_floor}"/>'
    )

    # --------------------------------------
    # 4.3. 绘制引道连接 (Draw Driveway Connections)
    # --------------------------------------
    d_p = [
        (mid_x + nx * 5 - ux * 4, mid_y + ny * 5 - uy * 4),
        (mid_x + nx * 12 - ux * 4, mid_y + ny * 12 - uy * 4),
        (mid_x + nx * 12 + ux * 4, mid_y + ny * 12 + uy * 4),
        (mid_x + nx * 5 + ux * 4, mid_y + ny * 5 + uy * 4),
    ]
    shape_driveway = " ".join([f"{p[0]:.2f},{p[1]:.2f}" for p in d_p])
    xml_elements.append(
        f'    <poly id="driveway_{spot_id}" color="40,40,40" fill="true" layer="1" shape="{shape_driveway}"/>'
    )

    # --------------------------------------
    # 4.4. 绘制边界围墙 (Draw Boundary Walls)
    # --------------------------------------
    w_p = [
        (mid_x + nx * 12 - ux * 4, mid_y + ny * 12 - uy * 4),
        (mid_x + nx * 12 - ux * 35, mid_y + ny * 12 - uy * 35),
        (mid_x + nx * 55 - ux * 35, mid_y + ny * 55 - uy * 35),
        (mid_x + nx * 55 + ux * 35, mid_y + ny * 55 + uy * 35),
        (mid_x + nx * 12 + ux * 35, mid_y + ny * 12 + uy * 35),
        (mid_x + nx * 12 + ux * 4, mid_y + ny * 12 + uy * 4),
    ]
    shape_wall = " ".join([f"{p[0]:.2f},{p[1]:.2f}" for p in w_p])
    xml_elements.append(
        f'    <poly id="wall_{spot_id}" color="200,200,200" fill="false" lineWidth="2" layer="2" shape="{shape_wall}"/>'
    )

    # --------------------------------------
    # 4.5. 创建停车区域逻辑入口 (Logical Entrance Creation)
    # --------------------------------------
    xml_elements.append(
        f'    <parkingArea id="{spot_id}" lane="{eid}_0" startPos="{L / 2 - 1.5}" endPos="{L / 2 + 1.5}" roadsideCapacity="0" onRoad="false">'
    )

    # --------------------------------------
    # 4.6. 车位布局设计 (Parking Spots Layout)
    # --------------------------------------
    for row_idx, depth in enumerate([22, 45]):
        for col in range(20):
            if row_idx == 0 and col in [9, 10]:
                continue

            sx, sy = (
                mid_x + nx * depth + ux * (col - 9.5) * 3.2,
                mid_y + ny * depth + uy * (col - 9.5) * 3.2,
            )
            angle = park_angle if row_idx == 0 else (park_angle + 180) % 360
            xml_elements.append(
                f'        <space x="{sx:.2f}" y="{sy:.2f}" angle="{angle:.2f}" width="2.8" length="5.5"/>'
            )
    xml_elements.append("    </parkingArea>")

# ==========================================
# 5. 路边停车位逻辑生成 (On-street Parking Generation)
# ==========================================
edge_spot_counts = defaultdict(int)
for i in range(800):
    edge = random.choice(on_street_pool)
    offset = 15 + (edge_spot_counts[edge] * 8)
    edge_spot_counts[edge] += 1

    insert_values.append(f"    ('on_street_{i}', '{edge}', 'on-street', 1, 5.00, 5.00)")
    xml_elements.append(
        f'    <parkingArea id="on_street_{i}" lane="{edge}_0" startPos="{offset}" endPos="{offset + 6}" roadsideCapacity="1" onRoad="false" width="3.5" angle="0"/>'
    )

# ==========================================
# 6. 数据写入文件 (Data Writing)
# ==========================================
sql_lines.append(",\n".join(insert_values) + ";")
with open(OUTPUT_SQL, "w", encoding="utf-8") as f:
    f.write("\n".join(sql_lines))

xml_elements.append("</additional>")
with open(OUTPUT_ADD_XML, "w", encoding="utf-8") as f:
    f.write("\n".join(xml_elements))

print(
    "✅ 数据已成功生成并保存到文件！\n"
    " 请检查输出目录中的 schema.sql 和 parking.add.xml 文件。"
)
