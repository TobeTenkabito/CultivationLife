"""A carried lower-world field has a study view without bypassing combat gates."""
from pathlib import Path
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.system.spirit_voisinage import player_source
from cultivation_life.system.aperture_resources import energy_state
from cultivation_life.system.immortal_aperture import public_aperture
from cultivation_life.ui_preferences import load_ui_preferences, write_ui_preferences

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('world,path',[('spirit','dao'),('true_demon','demonic'),
    ('monster_realm','monster'),('phantom_underworld','ghost'),('hell','ghost')])
@pytest.mark.parametrize('rank',[1,3,4,9])
def test_secondary_custom_manual_is_visible_before_and_after_unlock(tmp_path,world,path,rank):
    engine=GameEngine(ROOT,tmp_path)
    view=engine.create_game('灵域前尘','otherworld',path,280,
        monster_species_id='fox' if path=='monster' else None,
        custom_start=dict(world=world,realm_index=8,domain_rank=rank,tendency='strike'))
    game=engine.store.load(view['id'])
    snapshot=game.to_dict()
    info=public_aperture(game.player,game)
    assert info['lower'] and info['spirit_studies']
    assert info['spirit_studies'][0]['level']==rank
    assert info['available']==(rank>=4)
    assert bool(player_source(game).voisinages)==(rank>=4)
    assert (energy_state(game.player) is not None)==(rank>=4)
    if rank>=4:
        assert info['field'] and info['current']==60
    else:
        with pytest.raises(ValueError,match='四级'):
            engine.aperture_action(game.id,'refine')
    assert game.to_dict()==snapshot
    # get_game also prepares ordinary world/war state; purity is checked above
    # on the field projection itself, rather than that unrelated preparation.
    loaded=engine.get_game(game.id)
    assert loaded['aperture']['spirit_studies']==info['spirit_studies']

def test_navigation_preferences_survive_theme_updates_and_restart(tmp_path):
    choices={'pins':['map','spirit-voisinage'],'recent':['inventory']}
    assert write_ui_preferences(tmp_path,{'navigation':choices})['navigation']==choices
    write_ui_preferences(tmp_path,{'theme':'b'})
    loaded=load_ui_preferences(tmp_path)
    assert loaded['theme']=='b' and loaded['navigation']==choices
    loaded['navigation']['pins'].clear()
    assert load_ui_preferences(tmp_path)['navigation']==choices

@pytest.mark.parametrize('bad',[None,{}, {'pins':['map']*2,'recent':[]},
    {'pins':['map']*9,'recent':[]},{'pins':['/api/games'],'recent':[]},
    {'pins':[],'recent':['x']*5},{'pins':'map','recent':[]}])
def test_invalid_navigation_preferences_do_not_overwrite_file(tmp_path,bad):
    write_ui_preferences(tmp_path,{'theme':'f'})
    path=tmp_path/'data/ui_preferences.json';before=path.read_bytes()
    with pytest.raises(ValueError):write_ui_preferences(tmp_path,{'navigation':bad})
    assert path.read_bytes()==before
