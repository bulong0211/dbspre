import warnings

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from connection import get_db_connection

# -----------------------------------------------------------------------------
# Streamlit 页面基础配置
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Smart Parking Performance Dashboard", page_icon="🚗", layout="wide"
)

# 忽略所有警告信息
warnings.filterwarnings("ignore")


@st.cache_data(ttl=5)
def fetch_data():
    """
    连接数据库并拉取聚合后的仿真指标数据。
    配置了 5 秒的短效缓存机制以支持流畅的交互和实时刷新。
    """
    try:
        conn = get_db_connection()

        # 通过 SQL 查询从日志中聚合关键性能指标
        query = """
            SELECT 
                scenario, 
                COUNT(vehicle_id) as total_cars,
                SUM(CASE WHEN final_spot_id IS NOT NULL THEN 1 ELSE 0 END) as parked_cars,
                SUM(CASE WHEN final_spot_id IS NULL THEN 1 ELSE 0 END) as failed_cars,
                AVG(CASE WHEN final_spot_id IS NOT NULL THEN search_time_sec ELSE NULL END) as avg_search_parked,
                AVG(search_time_sec) as avg_search_all,
                SUM(total_fuel_mg) / 1000000.0 as total_fuel_kg,
                SUM(cruising_distance_m) / 1000.0 as total_dist_km
            FROM Cruising_Logs
            GROUP BY scenario
            ORDER BY scenario ASC;
        """
        df = pd.read_sql(query, conn)
        conn.close()

        # 映射数据库场景名称为易于阅读的 UI 标签
        df["scenario"] = df["scenario"].replace(
            {
                "Baseline": "场景 A (盲目寻找)",
                "Smart_Booking_Priced": "场景 B (智能定价)",
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

# 校验并展示数据不全的告警状态
if df.empty or len(df) < 2:
    st.warning("⚠️ 数据不足，请确保场景 A 和 B 的仿真均已完成并写入数据库。")
    if st.button("🔄 刷新数据"):
        st.cache_data.clear()
else:
    # 提取多场景数据用以横向对比
    row_A = df[df["scenario"] == "场景 A (盲目寻找)"].iloc[0]
    row_B = df[df["scenario"] == "场景 B (智能定价)"].iloc[0]

    st.markdown("### 📊 核心指标看板 (KPIs)")

    # 渲染顶部核心数据指标块 (Metric Widgets)
    col1, col2, col3, col4 = st.columns(4)

    success_A = (row_A["parked_cars"] / row_A["total_cars"]) * 100
    success_B = (row_B["parked_cars"] / row_B["total_cars"]) * 100

    fuel_saved = row_A["total_fuel_kg"] - row_B["total_fuel_kg"]
    fuel_saved_pct = (
        (fuel_saved / row_A["total_fuel_kg"]) * 100 if row_A["total_fuel_kg"] > 0 else 0
    )
    dist_saved = row_A["total_dist_km"] - row_B["total_dist_km"]

    with col1:
        st.metric(
            label="成功泊入率",
            value=f"{success_B:.1f}%",
            delta=f"{success_B - success_A:.1f}% （相比场景 A）",
        )
    with col2:
        st.metric(
            label="全局平均寻车耗时",
            value=f"{row_B['avg_search_all']:.1f} 秒",
            delta=f"{row_B['avg_search_all'] - row_A['avg_search_all']:.1f} 秒 （相比场景 A）",
            delta_color="inverse",
        )
    with col3:
        st.metric(
            label="系统总油耗",
            value=f"{row_B['total_fuel_kg']:.2f} kg",
            delta=f"{row_B['total_fuel_kg'] - row_A['total_fuel_kg']:.2f} kg （相比场景 A）",
            delta_color="inverse",
        )
    with col4:
        st.metric(
            label="无效巡航里程",
            value=f"{row_B['total_dist_km']:.1f} km",
            delta=f"{-row_A['total_dist_km']:.1f} km （相比场景 A）",
            delta_color="inverse",
        )

    st.divider()

    # -------------------------------------------------------------------------
    # 数据可视化图表绘制
    # -------------------------------------------------------------------------
    st.markdown("### 📈 维度深度对比")
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        # 构建吞吐量与死锁状态的堆叠柱状图
        fig_cars = go.Figure(
            data=[
                go.Bar(
                    name="成功入库",
                    x=df["scenario"],
                    y=df["parked_cars"],
                    marker_color="#2ecc71",
                ),
                go.Bar(
                    name="拥堵死锁/失败",
                    x=df["scenario"],
                    y=df["failed_cars"],
                    marker_color="#e74c3c",
                ),
            ]
        )
        fig_cars.update_layout(
            barmode="stack", title="系统吞吐量与死锁车辆数对比", template="plotly_white"
        )
        st.plotly_chart(fig_cars, use_container_width=True)

    with col_chart2:
        # 构建寻车时间成本的双柱对比图，直观揭示系统性偏差
        fig_time = go.Figure(
            data=[
                go.Bar(
                    name="成功者平均耗时",
                    x=df["scenario"],
                    y=df["avg_search_parked"],
                    marker_color="#3498db",
                ),
                go.Bar(
                    name="全局平均耗时 (含死锁)",
                    x=df["scenario"],
                    y=df["avg_search_all"],
                    marker_color="#f39c12",
                ),
            ]
        )
        fig_time.update_layout(
            barmode="group",
            title="寻车时间成本对比 (幸存者偏差分析)",
            template="plotly_white",
        )
        st.plotly_chart(fig_time, use_container_width=True)

    st.markdown("---")

    # -------------------------------------------------------------------------
    # 核心结论
    # -------------------------------------------------------------------------
    st.markdown("### 💡 核心结论")
    st.info(
        f"**✅ 吞吐量突破：** 传统盲目模式下，因路网拥堵死锁导致部分车辆 ({row_A['failed_cars']:.0f} 辆) 无法停车；本系统将停车成功率从 **{success_A:.1f}%** 跃升至 **{success_B:.1f}%**。"
    )
    st.info(
        f"**✅ 时间成本优化：** 智能模式显著降低了寻车时间，全局平均寻车耗时从 **{row_A['avg_search_all']:.1f} 秒** 下降至 **{row_B['avg_search_all']:.1f} 秒**，彻底消除了幸存者偏差带来的时间成本误判。"
    )
    st.info(
        f"**✅ 环境经济价值：** 动态定价与预订机制消灭了 **{dist_saved:.1f}** 公里的无效巡航里程，实现系统级减排 **{fuel_saved_pct:.2f}%**！"
    )

    st.markdown("---")

    # 渲染底部提示信息与手动干预控件
    col_bottom1, col_bottom2 = st.columns([8, 2])
    with col_bottom1:
        st.caption(
            "注：指标『全局平均耗时』将因拥堵导致超时被系统踢出的车辆也纳入了时间与油耗成本计算，更客观地反映了真实城市路网在极端盲目寻车下的崩溃代价。"
        )
