"""
一键准备仿真环境脚本 (Simulation Preparation Script)

该脚本封装了以下步骤：
1. 生成基础城市路网 (调用 generate_network.ps1)
2. 生成停车场和对应的 SQL 数据 (调用 generate_parking.py)
3. 生成向 CBD 汇聚的交通流数据 (调用 generate_traffic.py)
4. 初始化数据库并导入数据 (调用 init_db.py)
"""

import subprocess
import sys
from pathlib import Path

def run_step(step_name, cmd, cwd=None):
    print(f"\n{'='*60}\n🚀 {step_name}\n{'='*60}")
    try:
        subprocess.run(cmd, check=True, cwd=cwd)
    except subprocess.CalledProcessError as e:
        print(f"\n❌ 错误: {step_name} 失败，退出码: {e.returncode}")
        sys.exit(1)

def main():
    scripts_dir = Path(__file__).resolve().parent
    root_dir = scripts_dir.parent

    # 1. 生成基础城市路网
    run_step(
        "1. 生成基础城市路网",
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(scripts_dir / "generate_network.ps1")],
        cwd=root_dir
    )

    # 2. 生成停车场
    run_step(
        "2. 生成停车场和对应的 SQL 数据",
        [sys.executable, str(scripts_dir / "generate_parking.py")],
        cwd=root_dir
    )

    # 3. 生成向 CBD 汇聚的交通流数据
    run_step(
        "3. 生成向 CBD 汇聚的交通流数据",
        [sys.executable, str(scripts_dir / "generate_traffic.py")],
        cwd=root_dir
    )

    # 4. 初始化数据库并录入数据
    run_step(
        "4. 初始化数据库并录入数据",
        [sys.executable, str(scripts_dir / "init_db.py")],
        cwd=root_dir
    )

    print(f"\n{'='*60}\n✅ 所有仿真实验前的准备工作已完成！\n{'='*60}")

if __name__ == "__main__":
    main()
