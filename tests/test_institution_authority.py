"""Base institutional authority works without any DLC adapter or content."""
from pathlib import Path
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.system import institution_authority as authority
from cultivation_life.system.economy.ledger import balance


def test_base_authority_original_funds_handover_and_duplicate_roles(tmp_path,monkeypatch):
    engine=GameEngine(Path(__file__).resolve().parents[1],tmp_path)
    game=engine._load(engine.create_game('本体授权','supreme_metal','dao',372,preset_id='core')['id'])
    from cultivation_life.content_registry import WORLD_SYSTEMS
    for key in ('asura_manifestation','asura_governorship','yaochi_westward'):
        monkeypatch.setitem(WORLD_SYSTEMS[key],'enabled',False)
    original=game.player.location_id
    def create(identity):
        return authority.create(game,identity=identity,provider='base-test',name='公共事务署',
            world='human',location=original,owner=dict(kind='background',id='test'),
            source='background:human',building_id='public:'+identity,city_id='city:test')
    first,second=create('first'),create('second')
    cash=balance(game,'background:human')
    authority.nominate(game,first,'player',20)
    assert game.player.location_id==original and balance(game,first['wallet'])==0
    with pytest.raises(ValueError):authority.assume(game,first,'player','celestial',original)
    authority.assume(game,first,'player','human',original)
    with pytest.raises(ValueError):authority.nominate(game,second,'player',20)
    authority.fund(game,first,'background:human',1000)
    assert balance(game,'background:human')==cash-1000
    authority.revoke(game,first)
    assert not authority.effective(game,first) and first['controller']=='player'
    with pytest.raises(ValueError):authority.nominate(game,first,'player',20)
    authority.return_funds(game,first)
    authority.relinquish(game,first,'player')
    assert balance(game,'background:human')==cash
    authority.nominate(game,second,'player',20)
    assert GameState.from_dict(game.to_dict()).economy_v2==game.economy_v2
