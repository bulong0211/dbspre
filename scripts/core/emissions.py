"""Vehicle-level environmental metric collection helpers."""

import traci.constants as tc


EMISSION_SUB_VARS = [
    tc.VAR_FUELCONSUMPTION,
    tc.VAR_CO2EMISSION,
    tc.VAR_COEMISSION,
    tc.VAR_HCEMISSION,
    tc.VAR_NOXEMISSION,
    tc.VAR_PMXEMISSION,
    tc.VAR_NOISEEMISSION,
]


def init_environment_stats():
    return {
        "total_fuel": 0.0,
        "total_co2": 0.0,
        "total_co": 0.0,
        "total_hc": 0.0,
        "total_nox": 0.0,
        "total_pmx": 0.0,
        "total_noise": 0.0,
        "noise_samples": 0,
    }


def accumulate_environment(stats, data):
    stats["total_fuel"] = stats.get("total_fuel", 0.0) + data.get(
        tc.VAR_FUELCONSUMPTION, 0.0
    )
    stats["total_co2"] = stats.get("total_co2", 0.0) + data.get(
        tc.VAR_CO2EMISSION, 0.0
    )
    stats["total_co"] = stats.get("total_co", 0.0) + data.get(tc.VAR_COEMISSION, 0.0)
    stats["total_hc"] = stats.get("total_hc", 0.0) + data.get(tc.VAR_HCEMISSION, 0.0)
    stats["total_nox"] = stats.get("total_nox", 0.0) + data.get(
        tc.VAR_NOXEMISSION, 0.0
    )
    stats["total_pmx"] = stats.get("total_pmx", 0.0) + data.get(
        tc.VAR_PMXEMISSION, 0.0
    )

    if tc.VAR_NOISEEMISSION in data:
        stats["total_noise"] = stats.get("total_noise", 0.0) + data[
            tc.VAR_NOISEEMISSION
        ]
        stats["noise_samples"] = stats.get("noise_samples", 0) + 1


def environment_log_values(stats):
    samples = stats.get("noise_samples", 0)
    avg_noise = stats.get("total_noise", 0.0) / samples if samples else 0.0
    return {
        "total_fuel": stats.get("total_fuel", 0.0),
        "total_co2": stats.get("total_co2", 0.0),
        "total_co": stats.get("total_co", 0.0),
        "total_hc": stats.get("total_hc", 0.0),
        "total_nox": stats.get("total_nox", 0.0),
        "total_pmx": stats.get("total_pmx", 0.0),
        "avg_noise": avg_noise,
    }
