"""Strict evidence for the user-authorized map-only 2.13.1 release."""
import hashlib,json,xml.etree.ElementTree as ET
from pathlib import Path
from scripts.release_evidence import require,inputs_digest
TEST_MODULES=('test_maps_2131','test_map_system','test_territory_system','test_caravan_economy','test_economy_network_expansion','test_world_transition_system','test_spatial_talismans','test_release_211','test_release_212','test_release_2130','test_windows_release_evidence','test_android_release_checks')
ART_MODULES=('test_maps_2131','test_maps_2132','test_map_system','test_release_212','test_windows_release_evidence','test_android_release_checks')
PROFILES={'2.13.1':{'modules':TEST_MODULES,'native_cases':44},'2.13.2':{'modules':ART_MODULES,'native_cases':14}}
BROWSERS=('maps','territory','map-directory','events')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def validate(root,version):
 require(version in PROFILES,'Map-only release scope is registered only for 2.13.1 and 2.13.2');rid=version.replace('.','');profile=PROFILES[version]
 path=root/f'build/map-release-{rid}.json';require(path.is_file(),'Missing map-release verification receipt')
 r=json.loads(path.read_text(encoding='utf8'));require(r.get('version')==version and r.get('scope')=='maps' and r.get('full_repository_regression') is False,'Invalid map-only scope')
 current=inputs_digest(root);require(r.get('inputs_sha256')==current,'Map release source changed after verification')
 checks=r.get('checks',[]);required={'domains','check_world_transition_contract','check_module_dependencies','check_documentation',*BROWSERS}
 require({x.get('name') for x in checks}==required,'Incomplete map-release checks')
 for c in checks:
  require(c.get('exit_code')==0 and c.get('inputs_sha256')==current,'Failed or stale check: '+str(c.get('name')))
  log=root/c['log'];require(log.is_file() and digest(log)==c.get('sha256'),'Changed check evidence: '+c['name'])
 cases=ET.parse(root/f'build/maps-{rid}-tests.xml').getroot().findall('.//testcase');require(bool(cases),'No map regression cases')
 require(all(c.find('failure') is None and c.find('error') is None and c.find('skipped') is None for c in cases),'Map regression contains a failure or skip')
 modules={c.get('classname','').split('.')[1] for c in cases if c.get('classname','').startswith('tests.')};require(set(profile['modules'])<=modules,'Missing required map regression modules')
 require(digest(root/f'build/maps-{rid}-tests.xml')==r.get('pytest_xml_sha256'),'Changed map regression XML')
 report=json.loads((root/f'build/maps-{rid}/report.json').read_text(encoding='utf8'));rows=report.get('cases',[])
 require(report.get('passed') and report.get('inputs_sha256')==current and len(rows)==88,'Eleven-world map browser check must cover 88 cases')
 require({x['world'] for x in rows}=={'human','demon','spirit','true_demon','monster_realm','phantom_underworld','hell','celestial','asura','nether','reincarnation'} and {x['theme'] for x in rows}==set('abdf'),'Incomplete world/theme browser coverage')
 require(digest(root/f'build/maps-{rid}/report.json')==r.get('browser_report_sha256'),'Changed map browser report')
 r['passed_tests']=len(cases);r['browser_cases']=len(rows);return r
