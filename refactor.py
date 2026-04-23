import os
import shutil
from pathlib import Path

base_dir = Path(r"d:\WorkSpace\Ajou\dbspre")
src_dbspre = base_dir / "src" / "dbspre"
scripts_dir = base_dir / "scripts"
configs_dir = base_dir / "configs"

scripts_dir.mkdir(exist_ok=True)
configs_dir.mkdir(exist_ok=True)

src_configs = src_dbspre / "configs"
if src_configs.exists():
    for f in src_configs.iterdir():
        shutil.move(str(f), configs_dir / f.name)
    src_configs.rmdir()

schema_sql = src_dbspre / "database" / "schema.sql"
if schema_sql.exists():
    shutil.move(str(schema_sql), configs_dir / "schema.sql")

init_db = src_dbspre / "database" / "init.py"
if init_db.exists():
    shutil.move(str(init_db), scripts_dir / "init_db.py")

init_dir = src_dbspre / "simulator" / "init"
if init_dir.exists():
    if (init_dir / "net.ps1").exists():
        shutil.move(str(init_dir / "net.ps1"), scripts_dir / "generate_network.ps1")
    if (init_dir / "parking.py").exists():
        shutil.move(str(init_dir / "parking.py"), scripts_dir / "generate_parking.py")
    if (init_dir / "traffic.py").exists():
        shutil.move(str(init_dir / "traffic.py"), scripts_dir / "generate_traffic.py")

run_dir = src_dbspre / "simulator" / "run"
if run_dir.exists():
    for f in run_dir.iterdir():
        if f.name == "analyze_results.py":
            shutil.move(str(f), scripts_dir / "analyze_results.py")
        elif f.name == "dashboard.py":
            shutil.move(str(f), scripts_dir / "run_dashboard.py")
        elif f.name == "reset_database.py":
            shutil.move(str(f), scripts_dir / "reset_db.py")
        elif f.name == "scenario_A_baseline.py":
            shutil.move(str(f), scripts_dir / "run_scenario_A_baseline.py")
        elif f.name == "scenario_B_smart.py":
            shutil.move(str(f), scripts_dir / "run_scenario_B_smart.py")

sim_dir = src_dbspre / "simulator"
if sim_dir.exists():
    shutil.rmtree(str(sim_dir))

def replace_in_file(path, old, new):
    if path.exists():
        content = path.read_text(encoding="utf-8")
        content = content.replace(old, new)
        path.write_text(content, encoding="utf-8")

replace_in_file(scripts_dir / "generate_network.ps1", "src/dbspre/configs/optimal_cbd.net.xml", "configs/optimal_cbd.net.xml")
replace_in_file(scripts_dir / "generate_parking.py", 'BASE_DIR / "database" / "schema.sql"', 'BASE_DIR / "configs" / "schema.sql"')
replace_in_file(scripts_dir / "generate_traffic.py", '.parent.parent.parent / "configs"', '.parent.parent / "configs"')
replace_in_file(scripts_dir / "run_scenario_A_baseline.py", '.parent.parent.parent / "configs"', '.parent.parent / "configs"')
replace_in_file(scripts_dir / "run_scenario_B_smart.py", '.parent.parent.parent / "configs"', '.parent.parent / "configs"')

if (scripts_dir / "init_db.py").exists():
    init_db_content = (scripts_dir / "init_db.py").read_text(encoding="utf-8")
    init_db_content = init_db_content.replace("from .connection import get_db_connection", "from dbspre.database.connection import get_db_connection\nfrom pathlib import Path")
    init_db_content = init_db_content.replace('SQL_FILE = "./schema.sql"', 'SQL_FILE = Path(__file__).resolve().parent.parent / "configs" / "schema.sql"')
    (scripts_dir / "init_db.py").write_text(init_db_content, encoding="utf-8")

db_init = src_dbspre / "database" / "__init__.py"
if db_init.exists():
    db_init.write_text('from .connection import get_db_connection\n\n__all__ = ["get_db_connection"]\n', encoding="utf-8")

print("Refactoring complete.")