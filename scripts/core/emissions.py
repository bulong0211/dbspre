"""Vehicle-level environmental metric collection helpers."""

import traci.constants as tc


EMISSION_SUB_VARS = [
    tc.VAR_FUELCONSUMPTION,
    tc.VAR_CO2EMISSION,
    tc.VAR_NOXEMISSION,
    tc.VAR_PMXEMISSION,
]


def init_environment_stats():
    """返回车辆级排放累计字段的初始值。"""
    return {
        "total_fuel": 0.0,
        "total_co2": 0.0,
        "total_nox": 0.0,
        "total_pmx": 0.0,
    }


def accumulate_environment(stats, data):
    """从 TraCI 订阅结果中累加单步燃油与污染物排放。"""
    stats["total_fuel"] = stats.get("total_fuel", 0.0) + data.get(
        tc.VAR_FUELCONSUMPTION, 0.0
    )
    stats["total_co2"] = stats.get("total_co2", 0.0) + data.get(
        tc.VAR_CO2EMISSION, 0.0
    )
    stats["total_nox"] = stats.get("total_nox", 0.0) + data.get(
        tc.VAR_NOXEMISSION, 0.0
    )
    stats["total_pmx"] = stats.get("total_pmx", 0.0) + data.get(
        tc.VAR_PMXEMISSION, 0.0
    )


def environment_log_values(stats):
    """提取写入数据库所需的排放累计值。"""
    return {
        "total_fuel": stats.get("total_fuel", 0.0),
        "total_co2": stats.get("total_co2", 0.0),
        "total_nox": stats.get("total_nox", 0.0),
        "total_pmx": stats.get("total_pmx", 0.0),
    }
