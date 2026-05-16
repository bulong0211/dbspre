import warnings

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from core.connection import get_db_connection
from core.db_ops import ensure_simulation_runs_table

# -----------------------------------------------------------------------------
# Streamlit 页面基础配置
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Smart Parking Performance Dashboard", page_icon="🚗", layout="wide"
)

warnings.filterwarnings("ignore")


def _format_duration(seconds):
    seconds = 0 if pd.isna(seconds) else int(round(seconds))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours}h {minutes}m {secs}s"


@st.cache_data(ttl=5)
def fetch_data():
    """
    连接数据库并拉取聚合后的仿真指标数据。
    当前核心比较口径为：两场景均能完成全部车辆停放时，比较全局完成时间。
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_simulation_runs_table(cursor)
        conn.commit()

        query = """
            WITH latest_runs AS (
                SELECT DISTINCT ON (scenario)
                    scenario,
                    completion_time_sec,
                    total_vehicles,
                    parked_vehicles,
                    failed_vehicles,
                    parking_rate
                FROM Simulation_Runs
                ORDER BY scenario, created_at DESC, run_id DESC
            ),
            log_metrics AS (
                SELECT
                    scenario,
                    COUNT(vehicle_id) AS logged_cars,
                    AVG(search_time_sec) AS avg_search_all,
                    SUM(total_fuel_mg) / 1000000.0 AS total_fuel_kg,
                    SUM(cruising_distance_m) / 1000.0 AS total_dist_km
                FROM Cruising_Logs
                GROUP BY scenario
            )
            SELECT
                COALESCE(r.scenario, l.scenario) AS scenario,
                COALESCE(r.total_vehicles, l.logged_cars, 0) AS total_cars,
                COALESCE(r.parked_vehicles, 0) AS parked_cars,
                COALESCE(r.failed_vehicles, 0) AS failed_cars,
                COALESCE(r.parking_rate, 0) AS parking_rate,
                r.completion_time_sec,
                l.avg_search_all,
                COALESCE(l.total_fuel_kg, 0) AS total_fuel_kg,
                COALESCE(l.total_dist_km, 0) AS total_dist_km
            FROM latest_runs r
            FULL OUTER JOIN log_metrics l ON r.scenario = l.scenario
            ORDER BY scenario ASC;
        """
        df = pd.read_sql(query, conn)
        cursor.close()
        conn.close()

        df["scenario"] = df["scenario"].replace(
            {
                "Baseline": "场景 A (盲目寻找)",
                "Smart_Booking_Priced": "场景 B (智能预订)",
            }
        )
        return df
    except Exception as e:
        st.error(f"数据库连接失败: {e}")
        return pd.DataFrame()


# -----------------------------------------------------------------------------
# 仪表盘主视图渲染逻辑
# -----------------------------------------------------------------------------
st.title("🚗 Smart Parking Performance Dashboard")
st.markdown("基于 SUMO 交通仿真与 PostgreSQL 数据库的性能评估")

df = fetch_data()

if df.empty or len(df) < 2:
    st.warning("⚠️ 数据不足，请确保场景 A 和 B 均已完成并写入数据库。")
    if st.button("🔄 刷新数据"):
        st.cache_data.clear()
else:
    row_A = df[df["scenario"] == "场景 A (盲目寻找)"].iloc[0]
    row_B = df[df["scenario"] == "场景 B (智能预订)"].iloc[0]

    success_A = row_A["parking_rate"] * 100
    success_B = row_B["parking_rate"] * 100
    both_completed = abs(success_A - 100.0) < 1e-6 and abs(success_B - 100.0) < 1e-6
    completion_delta = row_B["completion_time_sec"] - row_A["completion_time_sec"]
    fuel_delta = row_B["total_fuel_kg"] - row_A["total_fuel_kg"]
    dist_saved = row_A["total_dist_km"] - row_B["total_dist_km"]

    st.markdown("### 📊 核心指标看板 (KPIs)")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="停放完成率",
            value=f"A {success_A:.1f}% / B {success_B:.1f}%",
            delta="两场景均完成停放" if both_completed else "存在未完成车辆",
        )
    with col2:
        st.metric(
            label="完成全部停放时间",
            value=_format_duration(row_B["completion_time_sec"]),
            delta=f"{completion_delta:.0f} 秒（相比场景 A）",
            delta_color="inverse",
        )
    with col3:
        st.metric(
            label="平均单车到达/寻位时间",
            value=f"{row_B['avg_search_all']:.1f} 秒",
            delta=f"{row_B['avg_search_all'] - row_A['avg_search_all']:.1f} 秒（相比场景 A）",
            delta_color="inverse",
        )
    with col4:
        st.metric(
            label="系统总油耗",
            value=f"{row_B['total_fuel_kg']:.2f} kg",
            delta=f"{fuel_delta:.2f} kg（相比场景 A）",
            delta_color="inverse",
        )

    st.info(
        "当前两种场景均可在 2 小时仿真上限内完成全部车辆停放，停放率本身不再构成有效区分；"
        "核心比较指标改为完成全部车辆停放所需的全局仿真时间。"
    )

    st.divider()

    st.markdown("### 📈 场景对比")
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        fig_completion = go.Figure(
            data=[
                go.Bar(
                    x=df["scenario"],
                    y=df["completion_time_sec"],
                    marker_color=["#64748b", "#0f766e"],
                    text=[_format_duration(v) for v in df["completion_time_sec"]],
                    textposition="outside",
                )
            ]
        )
        fig_completion.update_layout(
            title="完成全部车辆停放所需仿真时间",
            yaxis_title="仿真时间 (秒)",
            template="plotly_white",
        )
        st.plotly_chart(fig_completion, use_container_width=True)

    with col_chart2:
        fig_time = go.Figure(
            data=[
                go.Bar(
                    x=df["scenario"],
                    y=df["avg_search_all"],
                    marker_color=["#94a3b8", "#14b8a6"],
                    text=[f"{v:.1f}s" for v in df["avg_search_all"]],
                    textposition="outside",
                )
            ]
        )
        fig_time.update_layout(
            title="平均单车到达/寻位时间",
            yaxis_title="时间 (秒)",
            template="plotly_white",
        )
        st.plotly_chart(fig_time, use_container_width=True)

    col_chart3, col_chart4 = st.columns(2)

    with col_chart3:
        fig_status = go.Figure(
            data=[
                go.Bar(
                    name="成功停放",
                    x=df["scenario"],
                    y=df["parked_cars"],
                    marker_color="#22c55e",
                ),
                go.Bar(
                    name="失败/消失",
                    x=df["scenario"],
                    y=df["failed_cars"],
                    marker_color="#ef4444",
                ),
            ]
        )
        fig_status.update_layout(
            barmode="stack",
            title="停放结果数量",
            yaxis_title="车辆数",
            template="plotly_white",
        )
        st.plotly_chart(fig_status, use_container_width=True)

    with col_chart4:
        fig_environment = go.Figure(
            data=[
                go.Bar(
                    name="总油耗 (kg)",
                    x=df["scenario"],
                    y=df["total_fuel_kg"],
                    marker_color="#475569",
                ),
                go.Bar(
                    name="巡航距离 (km)",
                    x=df["scenario"],
                    y=df["total_dist_km"],
                    marker_color="#f59e0b",
                ),
            ]
        )
        fig_environment.update_layout(
            barmode="group",
            title="油耗与无效巡航距离",
            template="plotly_white",
        )
        st.plotly_chart(fig_environment, use_container_width=True)

    st.markdown("---")
    st.markdown("### 💡 结果解释")
    st.info(
        f"**停放率：** 场景 A 与场景 B 当前均达到 **{success_A:.1f}% / {success_B:.1f}%**，因此不再以成功率判断优劣。"
    )
    st.info(
        f"**完成时间：** 场景 A 完成全部车辆停放用时 **{_format_duration(row_A['completion_time_sec'])}**，"
        f"场景 B 用时 **{_format_duration(row_B['completion_time_sec'])}**。"
    )
    st.info(
        f"**运行成本：** 场景 B 相比场景 A 的总油耗变化为 **{fuel_delta:.2f} kg**，"
        f"无效巡航距离减少 **{dist_saved:.1f} km**。"
    )

    st.caption(
        "注：完成全部停放时间来自 Simulation_Runs.completion_time_sec，表示该场景完成所有已处理车辆停放所需的全局仿真时间。"
    )
