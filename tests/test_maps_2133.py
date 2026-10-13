"""Input-only map view changes."""
import shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_camera_view_math_and_existing_free_rotation():
 node=shutil.which('node');assert node
 for script,marker in [('map_view_checks_2133.js','View controls passed'),('map_camera_checks_2132.js','Trackball invariants passed')]:
  r=subprocess.run([node,str(ROOT/'tests'/script)],cwd=ROOT,capture_output=True,text=True)
  assert r.returncode==0,r.stdout+r.stderr
  assert marker in r.stdout
