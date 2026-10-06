"""Verify M2 representative real flows with each official DLC loaded alone."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CASES=[
    'test_heavens_m2_acceptance.py',
    'test_heavens_upper_worlds.py::test_real_world_year_and_local_material_eligibility',
    'test_heavens_mirror.py::test_real_peaceful_path_two_materials_record_and_stable_revisit',
    'test_heavens_mirror.py::test_real_combat_has_report_actual_cost_no_cultivator_kill_or_duplicate_loot',
    'test_heavens_ruins.py::test_replacement_costs_and_unique_return_transfer',
    'test_heavens_ruins.py::test_direct_take_real_combat_outage_then_restoration',
    'test_heavens_upkeep.py::test_all_four_worlds_finish_real_maintenance_without_new_people',
    'test_heavens_missions.py::test_four_real_npc_roundtrips_keep_identity_and_exact_budget',
    'test_heavens_migration.py::test_real_resident_settles_without_replacing_visitor',
]


def main():
    output=ROOT/'build/heavens-m2-dlc-matrix'
    output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for manifest in sorted((ROOT/'dlc').glob('*/manifest.json')):
        info=json.loads(manifest.read_text(encoding='utf-8'))
        started=time.perf_counter()
        with tempfile.TemporaryDirectory() as folder:
            app=Path(folder)
            shutil.copytree(ROOT/'content',app/'content')
            shutil.copytree(manifest.parent,app/'dlc'/manifest.parent.name)
            env={**os.environ,'CULTIVATION_APP_ROOT':str(app),'PYTHONIOENCODING':'utf-8'}
            code='''import json, sys, pytest
from cultivation_life.content_registry import EXTENSION_REPORT
loaded=[r['id'] for r in EXTENSION_REPORT if r['status']=='loaded']
assert loaded==[sys.argv[1]], EXTENSION_REPORT
print(json.dumps(EXTENSION_REPORT,ensure_ascii=False),flush=True)
raise SystemExit(pytest.main(sys.argv[2:]))
'''
            args=[sys.executable,'-c',code,info['id'],*[str(ROOT/'tests'/case) for case in CASES],
                  '-q','--disable-warnings','-o',f'cache_dir={app / "pytest-cache"}']
            with (output/(manifest.parent.name+'.log')).open('w',encoding='utf-8') as log:
                result=subprocess.run(args,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        row=dict(id=info['id'],version=info['version'],exit_code=result.returncode,seconds=round(time.perf_counter()-started,2))
        rows.append(row)
        (output/'report.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
        print(json.dumps(row),flush=True)
    if not rows or not all(row['exit_code']==0 for row in rows):raise SystemExit(1)


if __name__=='__main__':main()
