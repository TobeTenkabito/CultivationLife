"""Domain presentation follows real phase facts and never drives settlement."""
import copy
import random
from pathlib import Path
from unittest.mock import patch

import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.combat_visuals import report_visuals
from fixtures.visual_additions import prepare_domain_battle

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def engine(tmp_path_factory):
    return GameEngine(ROOT, tmp_path_factory.mktemp('domain-replay')/'saves')


@pytest.mark.parametrize('kind', ['control', 'contest', 'mutual', 'mixed'])
def test_real_domains_record_phases_and_stable_appearance(engine, kind, tmp_path):
    from cultivation_life.ui_preferences import write_ui_preferences
    settings=dict(outline='time',pattern='wood',palette='#a3b8c9',control='stars',density=76)
    write_ui_preferences(tmp_path, {'voisinage_appearance':settings})
    identity=engine.create_game('邻域回放','heavenly','dao',151,preset_id='core')['id']
    with patch('cultivation_life.runtime.persistence_root', return_value=tmp_path):
        report=prepare_domain_battle(engine,identity,kind)
    assert report['visual']['domains']['player']==settings
    rows=[r for r in report['rounds'] if r.get('voisinage',{}).get('animation')]
    assert rows and all(r['voisinage']['animation']['version']==1 for r in rows)
    if kind in {'control','mutual'}:
        assert rows[0]['voisinage']['animation']['effects']
        assert any(v['relation']=='dominated' for v in rows[0]['voisinage']['animation']['relations'].values())
    if kind=='mutual':
        assert len(rows[0]['voisinage']['animation']['effects'])==2
    if kind=='mixed':
        assert any(r.get('ordinary_exchange') for r in report['rounds'])
    game=engine.store.load(identity)
    assert game.last_combat_report==report
    before=copy.deepcopy(game.to_dict());rng=random.getstate()
    visual=report_visuals(game, {'target_name':'邻域演武'}, report, identity=report['visual'])
    assert visual==report['visual'] and game.to_dict()==before and random.getstate()==rng


def test_real_effects_capture_terminal_and_intervention():
    from test_domain_combat import capability, voisinage, unit, begin
    from cultivation_life.system.combat.voisinages import VoisinageBattle
    battle=VoisinageBattle([unit('player','player',capability()),unit('enemy','enemy')])
    begin(battle)
    facts=copy.deepcopy(battle.report()['animation'])
    assert facts['fields'][0]['owner']=='player'
    assert facts['effects'][0]['kind']=='suppress'
    assert facts['relations']['enemy']['relation']=='dominated'
    assert facts['effects'][0]['body_loss']==0
    begin(battle,2)
    assert facts['fields'][0]['sustained_rounds']==1
