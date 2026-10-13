"""Independent artwork and input-only camera behavior."""
import copy,hashlib,json,re,shutil,subprocess
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
from cultivation_life.system.map_system import MapCatalog
ROOT=Path(__file__).resolve().parents[1]
DOCUMENT=json.loads((ROOT/'content/maps.json').read_text(encoding='utf8'))
WORLDS=[w for w in DOCUMENT['worlds'] if w not in {'rift','lost'}]
DATA=json.loads((ROOT/'web/map-artwork-data.js').read_text(encoding='utf8').split('window.MapArtworkData=',1)[1].rstrip(';\n'))
@pytest.mark.parametrize('world',WORLDS)
def test_independent_material_is_local_safe_and_complete(world):
 art=DATA[world];target=ROOT/'web'/art['url'].split('?')[0].lstrip('/')
 svg=ET.parse(target).getroot()
 assert svg.attrib['data-world']==world
 assert len(svg.findall('.//{http://www.w3.org/2000/svg}path'))>=12
 metadata=json.loads(svg.find('{http://www.w3.org/2000/svg}metadata').text)
 assert metadata['world']==world and len(metadata['landmarks'])==4
 assert not any(n.tag.rsplit('}',1)[-1] in {'script','foreignObject','animate','image'} for n in svg.iter())
 assert all(not k.startswith('on') for n in svg.iter() for k in n.attrib)
 assert len(art['outlines'])>=4
 assert len(art['outline'])>=60 and art['width']>0 and art['height']>0
def test_worlds_are_separate_drawings_even_after_colors_are_removed():
 assert set(DATA)==set(WORLDS)
 signatures=set();coasts=set();landmarks=set()
 for w in WORLDS:
  svg=ET.parse(ROOT/'web/assets/maps'/f'{w}.svg').getroot()
  geometry=[(n.tag.rsplit('}',1)[-1],tuple(sorted((k,v) for k,v in n.attrib.items() if k in {'d','cx','cy','rx','ry','points'}))) for n in svg.iter() if any(k in n.attrib for k in {'d','cx','cy','points'})]
  signatures.add(hashlib.sha256(repr(geometry).encode()).hexdigest())
  coasts.add(tuple(tuple(p) for p in DATA[w]['outline']))
  landmarks.add(tuple(json.loads(svg.find('{http://www.w3.org/2000/svg}metadata').text)['landmarks']))
 assert len(signatures)==len(coasts)==len(landmarks)==11
def test_camera_follows_pointer_and_has_no_angle_clamp():
 node=shutil.which('node');assert node,'Node is required for the camera invariants'
 result=subprocess.run([node,str(ROOT/'tests/map_camera_checks_2132.js')],cwd=ROOT,capture_output=True,text=True)
 assert result.returncode==0,result.stdout+result.stderr
 assert 'Trackball invariants passed' in result.stdout
@pytest.mark.parametrize('world',WORLDS)
def test_artwork_view_does_not_change_routes_or_persistent_map_data(world):
 doc=copy.deepcopy(DOCUMENT);catalog=MapCatalog(doc);before=copy.deepcopy(doc)
 origin=catalog.default_location(world);first=catalog.public_map(world,origin,7,world);second=catalog.public_map(world,origin,7,world)
 assert first==second and doc==before
 for n in first['locations']:
  if n['id']!=origin:
   plan=catalog.travel_plan(world,origin,n['id'],7)
   assert n['route_ids']==list(plan.route) and n['travel_years']==plan.years

def inside_ground(point,ring):
 x,y=point;result=False
 for a,b in zip(ring,ring[1:]+ring[:1]):
  if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:result=not result
 return result

@pytest.mark.parametrize('world,grounds',[
 ('celestial',[(-720,-500),(-190,-860),(560,-760),(880,-350),(730,420),(190,690),(-600,430)]),
 ('asura',[(x+dx,y+dy) for x,y,r in [(-510,410,175),(350,-650,155),(590,340,170)] for dx,dy in [(r+16,0),(-r-16,0),(0,r*.7+16),(0,-r*.7-16)]]),
 ('human',[(540,-170),(635,-240),(730,-170),(705,-100),(565,-100)]),
 ('spirit',[(335,-750),(450,-830),(560,-750),(380,-655),(525,-655)]),
])
def test_iconic_building_grounds_survive_coastal_erosion(world,grounds):
 ring=DATA[world]['outline']
 # Check the actual known grounds, including the entire celestial terrace perimeter.
 for a,b in zip(grounds,grounds[1:]+grounds[:1]) if world=='celestial' else [(p,p) for p in grounds]:
  for i in range(21):
   p=[a[0]+(b[0]-a[0])*i/20,a[1]+(b[1]-a[1])*i/20]
   assert inside_ground(p,ring),(world,p,'landmark clipped by coast')

@pytest.mark.parametrize('world',WORLDS)
def test_mainland_shore_is_a_non_crossing_polygon(world):
 ring=DATA[world]['outline']
 def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
 for i,a in enumerate(ring):
  b=ring[(i+1)%len(ring)]
  for j in range(i+2,len(ring)):
   if i==0 and j==len(ring)-1:continue
   c=ring[j];d=ring[(j+1)%len(ring)]
   assert not (cross(a,b,c)*cross(a,b,d)<0 and cross(c,d,a)*cross(c,d,b)<0),(world,i,j)
