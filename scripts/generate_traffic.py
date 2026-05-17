"""
SUMO 交通流生成脚本 (Traffic Commute Simulator for SUMO)

本脚本读取 SUMO 路网文件，通过边界坐标分离出外围入口路段。
当前设定下整个路网均视为 CBD，车辆从外围入口驶入非入口路段，并按出发时间从小到大排序后输出为 XML 文件。
"""

import random
import xml.etree.ElementTree as ET
from pathlib import Path

# =============================================================================
# 1. 路径配置 (Configuration)
# =============================================================================
CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"
NET_FILE = CONFIG_DIR / "demo.net.xml"
OUTPUT_TRIPS = CONFIG_DIR / "demo.trips.xml"

# =============================================================================
# 2. 路网解析与边界坐标获取 (Network Parsing & Boundary Calculation)
# =============================================================================
try:
    tree = ET.parse(NET_FILE)
    root = tree.getroot()
except FileNotFoundError:
    print(f"ERROR: 找不到 {NET_FILE}")
    exit()

nodes = {}
for node in root.findall("junction"):
    if "type" in node.attrib and node.attrib["type"] != "internal":
        nodes[node.attrib["id"]] = (float(node.attrib["x"]), float(node.attrib["y"]))

min_x, max_x = min(p[0] for p in nodes.values()), max(p[0] for p in nodes.values())
min_y, max_y = min(p[1] for p in nodes.values()), max(p[1] for p in nodes.values())

# =============================================================================
# 3. 路段分类：边缘入口与 CBD 目的地 (Edge Classification: Entry vs CBD)
# =============================================================================
entry_edges = []
edge_data = {}

for edge in root.findall("edge"):
    if "function" not in edge.attrib:
        eid = edge.attrib["id"]
        fx, fy = nodes[edge.attrib["from"]]
        tx, ty = nodes[edge.attrib["to"]]
        edge_data[eid] = {
            "from": edge.attrib["from"],
            "to": edge.attrib["to"],
            "from_pos": (fx, fy),
            "to_pos": (tx, ty),
        }

        if fx <= min_x + 1 or fx >= max_x - 1 or fy <= min_y + 1 or fy >= max_y - 1:
            entry_edges.append(eid)

print(f"发现外围入口路段 (出生点): {len(entry_edges)} 条")

# =============================================================================
# 4. 通勤行程生成与排序 (Trip Generation & Sorting)
# =============================================================================
VEHICLE_COUNT = 2500
SIM_DURATION = 3600

all_edges = list(edge_data.keys())
destination_edges = [eid for eid in all_edges if eid not in set(entry_edges)]

if not entry_edges:
    raise RuntimeError("未找到外围入口路段，无法生成车辆出发边。")
if not destination_edges:
    destination_edges = all_edges
    print("WARNING: 未找到非入口目的地路段，目的地将回退为全路网随机路段。")

print(f"发现 CBD 目的地候选路段: {len(destination_edges)} 条")

trips_data = []
for i in range(VEHICLE_COUNT):
    start_edge = random.choice(entry_edges)
    end_edge = random.choice(destination_edges)
    depart_time = round(random.uniform(0, SIM_DURATION), 1)

    trips_data.append(
        {
            "id": f"veh_{i}",
            "depart": depart_time,
            "from": start_edge,
            "to": end_edge,
        }
    )

trips_data.sort(key=lambda x: x["depart"])

# =============================================================================
# 5. XML 格式化构建 (XML Formatting)
# =============================================================================
trips_xml = ["<trips>"]
trips_xml.append(
    '    <vType id="car" accel="2.6" decel="4.5" sigma="0.5" length="5" minGap="2.5" maxSpeed="13.89" color="0,255,0"/>'
)

for trip in trips_data:
    trips_xml.append(
        f'    <trip id="{trip["id"]}" type="car" depart="{trip["depart"]}" from="{trip["from"]}" to="{trip["to"]}"/>'
    )

trips_xml.append("</trips>")

# =============================================================================
# 6. 行程文件输出 (Output to File)
# =============================================================================
with open(OUTPUT_TRIPS, "w", encoding="utf-8") as f:
    f.write("\n".join(trips_xml))

print(f"成功！已生成 {VEHICLE_COUNT} 辆按时间排序的通勤行程。")
