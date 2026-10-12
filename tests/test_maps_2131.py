import copy,json,math
from pathlib import Path
import networkx as nx
import pytest
from cultivation_life.system.map_system import MapCatalog,MapContentError
ROOT=Path(__file__).resolve().parents[1]
DOCUMENT=json.loads((ROOT/'content/maps.json').read_text(encoding='utf8'))
WORLDS=[w for w in DOCUMENT['worlds'] if w not in {'rift','lost'}]
LOWER=['human','demon','spirit','true_demon','monster_realm','phantom_underworld','hell']
@pytest.mark.parametrize('world',LOWER)
def test_dense_center_and_sparse_but_cyclic_outskirts(world):
 d=DOCUMENT['worlds'][world];g=nx.Graph((r['from'],r['to']) for r in d['routes']);core=[n['id'] for n in d['locations'] if n['atlas']['region']=='core'];periphery=[n['id'] for n in d['locations'] if n['atlas']['region']=='outer']
 cg=g.subgraph(core);pg=g.subgraph(periphery)
 assert nx.is_connected(g)
 assert len(nx.cycle_basis(cg))>len(nx.cycle_basis(pg))>=1
 assert all(g.degree[n]<=3 for n in periphery)
 assert len([n for n in periphery if g.degree[n]==1])>=3
 assert d['default'] not in d['atlas']['centers']
 assert all(not next(n for n in d['locations'] if n['id']==c).get('min_realm_index') for c in d['atlas']['centers'])
@pytest.mark.parametrize('world',WORLDS)
def test_all_pairs_match_independent_weighted_graph_and_gates(world):
 catalog=MapCatalog(copy.deepcopy(DOCUMENT));d=DOCUMENT['worlds'][world];g=nx.Graph();g.add_weighted_edges_from((r['from'],r['to'],r['years']) for r in d['routes'])
 assert len(g.edges)==len(d['routes'])
 for origin in g:
  expected=nx.single_source_dijkstra_path_length(g,origin)
  for destination,cost in expected.items():
   if origin==destination:continue
   p=catalog.travel_plan(world,origin,destination,0)
   assert p.base_years==cost
   assert p.route[0]==origin and p.route[-1]==destination
   assert p.status==('lethal' if catalog.location(world,destination).get('min_realm_index',0)>0 else 'ok')
   assert p.years>=1
@pytest.mark.parametrize('world',WORLDS)
def test_new_location_and_absent_visual_metadata_remain_compatible(world):
 doc=copy.deepcopy(DOCUMENT);d=doc['worlds'][world];row=copy.deepcopy(d['locations'][0]);row['id']='future-location';row.pop('atlas',None);d['locations'].append(row);
 d['routes'].append({'from':d['default'],'to':row['id'],'years':3});catalog=MapCatalog(doc);before=copy.deepcopy(doc)
 public=catalog.public_map(world,d['default'],9,world)
 assert len(public['locations'])==len(d['locations']);assert public['atlas']==d['atlas']
 dest=next(n for n in public['locations'] if n['id']==row['id']);assert dest['route_ids']==[d['default'],row['id']]
 assert doc==before
 for location in d['locations']:location.pop('atlas',None)
 d.pop('atlas',None);MapCatalog(doc)
@pytest.mark.parametrize('position',[[0,0,float('nan')],[0,0,float('inf')],[True,0,1],[1,2],['1',0,0]])
def test_invalid_scene_coordinates_are_rejected(position):
 doc=copy.deepcopy(DOCUMENT);doc['worlds']['human']['locations'][0]['atlas']['position']=position
 with pytest.raises(MapContentError,match='三维坐标'):MapCatalog(doc)

@pytest.mark.parametrize('version',['2.13.0','3.0.0'])
def test_map_only_gate_rejects_unregistered_release(tmp_path,version):
 from scripts.map_release_evidence import validate
 with pytest.raises(RuntimeError,match='registered only'):validate(tmp_path,version)

@pytest.mark.parametrize('corruption',['stale','full','checks'])
def test_map_only_gate_rejects_stale_or_incomplete_evidence(tmp_path,monkeypatch,corruption):
 from scripts import map_release_evidence as ev
 monkeypatch.setattr(ev,'inputs_digest',lambda root:'current')
 (tmp_path/'build').mkdir()
 r=dict(version='2.13.1',scope='maps',full_repository_regression=False,inputs_sha256='current',checks=[])
 if corruption=='stale':r['inputs_sha256']='old'
 if corruption=='full':r['full_repository_regression']=True
 (tmp_path/'build/map-release-2131.json').write_text(json.dumps(r),encoding='utf8')
 with pytest.raises(RuntimeError):ev.validate(tmp_path,'2.13.1')

@pytest.mark.parametrize('world',WORLDS)
def test_outer_islands_share_real_locations_without_changing_graph(world):
 d=DOCUMENT['worlds'][world];groups={}
 for n in d['locations']:
  if n['atlas']['region']=='outer':groups.setdefault(n['atlas']['island'],[]).append(n)
 assert any(len(g)==2 for g in groups.values())
 assert any(len(g)==1 for g in groups.values())
 assert all(1<=len(g)<=2 for g in groups.values())
 catalog=MapCatalog(copy.deepcopy(DOCUMENT))
 public=catalog.public_map(world,d['default'],9,world)
 assert {n['id']:n.get('atlas') for n in public['locations']}=={n['id']:n.get('atlas') for n in d['locations']}
 for g in groups.values():
  if len(g)==2:
   assert math.dist(g[0]['atlas']['position'][:2],g[1]['atlas']['position'][:2])<260
   assert any({r['from'],r['to']}=={g[0]['id'],g[1]['id']} for r in d['routes'])
@pytest.mark.parametrize('island',[False,[],{},'', ' '])
def test_invalid_island_group_rejected(island):
 doc=copy.deepcopy(DOCUMENT);doc['worlds']['human']['locations'][0]['atlas']['island']=island
 with pytest.raises(MapContentError,match='岛屿'):MapCatalog(doc)

@pytest.mark.parametrize('world,sky,first,second',[
 ('spirit','expanse_spirit_3','expanse_spirit_2','expanse_spirit_4'),
 ('phantom_underworld','ancient_vine_bridge','myriad_spirit_forest','moon_insect_cavern'),
 ('celestial','expanse_celestial_14','expanse_celestial_13','expanse_celestial_15'),
 ('reincarnation','expanse_reincarnation_11','expanse_reincarnation_10','expanse_reincarnation_12'),
 ('monster_realm','worldwood_stair','qingqiu_mist_marsh','myriad_insect_cavern'),
])
def test_near_sky_bypass_is_authoritative_and_retains_destination_gate(world,sky,first,second):
 catalog=MapCatalog(copy.deepcopy(DOCUMENT))
 direct=next(r for r in DOCUMENT['worlds'][world]['routes'] if {r['from'],r['to']}=={first,second})
 plan=catalog.travel_plan(world,first,second,0)
 assert sky not in plan.route
 assert plan.base_years<=direct['years']
 target=catalog.location(world,sky)
 entered=catalog.travel_plan(world,first,sky,0)
 assert entered.status==('lethal' if target.get('min_realm_index',0) else 'ok')
