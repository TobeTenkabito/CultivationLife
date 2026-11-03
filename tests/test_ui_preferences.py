import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from cultivation_life.ui_preferences import DEFAULTS,load_ui_preferences,write_ui_preferences

def test_default_and_partial_updates_are_pixel_only(tmp_path):
    assert load_ui_preferences(tmp_path)==DEFAULTS
    assert DEFAULTS['pixel_art'] is True
    for palette in ('light','dark'):
        write_ui_preferences(tmp_path,{'pixel_theme':palette})
        assert load_ui_preferences(tmp_path)==DEFAULTS|{'pixel_theme':palette}
    write_ui_preferences(tmp_path,{'reduced_motion':True})
    assert load_ui_preferences(tmp_path)==DEFAULTS|{'pixel_theme':'dark','reduced_motion':True}

@pytest.mark.parametrize('payload',[{},[],{'theme':[]},{'theme':'b'},{'theme':'d'},{'theme':'f'},
    {'theme':'c'},{'theme':'e'},{'pixel_art':False},{'pixel_art':1},{'pixel_art':'true'},
    {'pixel_theme':[]},{'pixel_theme':'a'},{'compact_docks':1},{'reduced_motion':1},{'unknown':True}])
def test_retired_and_invalid_submissions_are_atomic(tmp_path,payload):
    write_ui_preferences(tmp_path,{'pixel_theme':'dark'});path=tmp_path/'data/ui_preferences.json';before=path.read_bytes()
    with pytest.raises(ValueError):write_ui_preferences(tmp_path,payload)
    assert path.read_bytes()==before

@pytest.mark.parametrize('old',['a','b','c','d','e','f'])
def test_old_preferences_cannot_restore_retired_layouts_or_rewrite_files_on_read(tmp_path,old):
    path=tmp_path/'data/ui_preferences.json';path.parent.mkdir()
    path.write_text(json.dumps(dict(theme=old,pixel_art=False,pixel_theme='dark',compact_docks=False,
        reduced_motion=True,navigation={'pins':['map'],'recent':[]})),encoding='utf8');before=path.read_bytes()
    actual=load_ui_preferences(tmp_path)
    assert actual==DEFAULTS|dict(pixel_theme='dark',compact_docks=False,reduced_motion=True,navigation={'pins':['map'],'recent':[]})
    assert path.read_bytes()==before

@pytest.mark.parametrize('raw',['broken','[]','null','{"theme":[],"reduced_motion":"true"}'])
def test_corrupt_preferences_default_to_new_light_ui(tmp_path,raw):
    path=tmp_path/'data/ui_preferences.json';path.parent.mkdir();path.write_text(raw,encoding='utf8')
    assert load_ui_preferences(tmp_path)==DEFAULTS

def test_concurrent_updates_preserve_saves_and_other_preferences(tmp_path):
    path=tmp_path/'data/saves/sentinel.json';path.parent.mkdir(parents=True);path.write_text('{"age":38}')
    write_ui_preferences(tmp_path,{'compact_docks':False,'navigation':{'pins':['map'],'recent':[]}})
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda t:write_ui_preferences(tmp_path,{'pixel_theme':t}),['light','dark']*10))
    saved=load_ui_preferences(tmp_path)
    assert saved['theme']=='a' and saved['pixel_art'] is True and not saved['compact_docks']
    assert saved['navigation']=={'pins':['map'],'recent':[]} and path.read_text()=='{"age":38}'
    assert not list((tmp_path/'data').glob('*.tmp'))
