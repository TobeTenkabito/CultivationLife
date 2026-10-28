"""Causal stories reject lookalikes, missing evidence and reordered histories."""
import copy
import pytest

from cultivation_life.achievement_stories import (
    soul_story, family_line_preserved, homecoming, three_sect_leaders, inherited_technique,
)
from cultivation_life.models import GameState, Player, SectState, HistoryRecord


def game():
    return GameState('story-test', 1, Player('沈砚', 'supreme_fire'), '', '')


def event(identity, result='settled', choice=None, **diff):
    return HistoryRecord(identity, 1, 20, '证据', choice, result, '不靠文案猜测', diff, [])


def test_soul_needs_structured_real_evidence_and_queries_are_pure():
    g = game()
    g.player.spirit_state = dict(mode='wandering', body_intact=False)
    g.history.append(event('SYS_SOUL'))
    assert not soul_story(g, 'body_destroyed')
    assert not soul_story(g, 'second_rescued')
    g.history.append(event('SYS_SOUL', body_destroyed=True, lost_realm=4))
    before = copy.deepcopy(g.to_dict())
    assert soul_story(g, 'body_destroyed')
    assert soul_story(g, 'body_destroyed', {'SYS_SOUL': g.history})
    assert not soul_story(g, 'second_rescued')
    assert g.to_dict() == before


@pytest.mark.parametrize('invalid', ['no_loss', 'wrong_host', 'below_rank', 'not_possessed', 'dead', 'wrong_order'])
def test_account_recovery_requires_loss_then_real_possession_of_current_host(invalid):
    g = game()
    loss = event('SYS_SOUL', body_destroyed=True, lost_realm=4)
    possession = event('SYS_CAPTIVE_ACTION', 'possessed', target_id='host')
    g.history = [loss, possession]
    g.player.realm_index = 4
    g.player.ghost_host_body = {'id': 'host'}
    assert soul_story(g, 'account_recovered')
    if invalid == 'no_loss': g.history = [possession]
    elif invalid == 'wrong_host': g.player.ghost_host_body['id'] = 'other'
    elif invalid == 'below_rank': g.player.realm_index = 3
    elif invalid == 'not_possessed': g.player.ghost_host_body = None
    elif invalid == 'dead': g.player.alive = False
    elif invalid == 'wrong_order': g.history.reverse()
    assert not soul_story(g, 'account_recovered')


def test_tian_keeps_original_name_and_rejects_using_rename_qualification():
    g = game()
    g.family = SectState('qi', '姜氏仙族', kind='family')
    g.family.heritage.update({
        'books': [], 'revision': 0, 'history': [],
        'line_successor': 'player', 'rename_available': True,
    })
    g.history = [event('SYS_FAMILY_LINE_SUCCESSION', 'succeeded', 'qi', successor='player')]
    before = copy.deepcopy(g.to_dict())
    assert family_line_preserved(g)
    assert g.family.name == '姜氏仙族' and g.to_dict() == before
    g.family.name = '田氏仙族'
    g.family.heritage['rename_available'] = False
    assert not family_line_preserved(g)


@pytest.mark.parametrize('invalid', ['npc_successor', 'no_succession', 'other_family', 'extinct', 'away'])
def test_tian_rejects_title_or_unrelated_lineage(invalid):
    g = game()
    g.family = SectState('qi', '姜氏', kind='family')
    g.family.heritage.update({
        'books': [], 'revision': 0, 'history': [],
        'line_successor': 'player', 'rename_available': True,
    })
    g.history = [event('SYS_FAMILY_LINE_SUCCESSION', 'succeeded', 'qi', successor='player')]
    if invalid == 'npc_successor': g.history[0].state_diff['successor'] = 'npc'
    elif invalid == 'no_succession': g.history.clear()
    elif invalid == 'other_family': g.family.id = 'other'
    elif invalid == 'extinct': g.family.extinct = True
    elif invalid == 'away': g.player.world = 'spirit'
    assert not family_line_preserved(g)


@pytest.mark.parametrize('invalid', ['custom_start', 'reverse_order', 'wrong_world', 'lateral', 'return_only', 'no_mode'])
def test_homecoming_requires_progression_then_true_descent_to_original_world(invalid):
    g = game()
    ascension = event('SYS_CELESTIAL_ASCENSION_COMPLETE', 'ascended', world=['spirit', 'celestial'])
    descent = event('SYS_CROSS_WORLD', 'returned_spirit', 'spirit', mode='sealed_descent')
    g.history = [ascension, descent]
    assert homecoming(g)
    if invalid == 'custom_start': g.history = [descent]
    elif invalid == 'reverse_order': g.history.reverse()
    elif invalid == 'wrong_world':
        descent.choice_id = 'human'; descent.result = 'returned_human'
    elif invalid == 'lateral': ascension.state_diff['world'] = ['human', 'demon']
    elif invalid == 'return_only': descent.state_diff['mode'] = 'sealed_return'
    elif invalid == 'no_mode': descent.state_diff.clear()
    assert not homecoming(g)


def test_leader_count_resets_on_departure_including_same_year_rejoin():
    g = game()
    g.sects['sect'] = SectState('sect', '听松宗')
    g.player.faction_id = 'sect'
    g.player.faction_join_age = 16
    dismissal = lambda: event('SYS_SECT_LEADER_DISMISSED', 'dismissed', sect_id='sect', joined_age=16)
    g.history = [dismissal(), dismissal()]
    assert not three_sect_leaders(g)
    g.history.append(dismissal())
    assert three_sect_leaders(g)
    g.history.append(event('SYS_PLAYER_LEAVE_FACTION', 'left', 'sect'))
    g.history.append(dismissal())
    assert not three_sect_leaders(g)


def test_inherited_shelf_alone_and_disabled_dlc_do_not_unlock(monkeypatch):
    from cultivation_life.system import authored_techniques as author
    from cultivation_life.content_registry import TECHNIQUE_CATALOG
    g = game()
    book = copy.deepcopy(next(iter(TECHNIQUE_CATALOG.values())))
    g.authored_techniques = dict(source_id='previous', inherited={book.id: {'origin': 'previous'}})
    monkeypatch.setattr(author, 'enabled', lambda: True)
    assert not inherited_technique(g, 1)
    g.player.known_techniques = [book]
    assert inherited_technique(g, 1)
    assert not inherited_technique(g, 9)
    book.level = 9
    assert inherited_technique(g, 9)
    g.authored_techniques['inherited'][book.id]['origin'] = 'unrelated'
    assert not inherited_technique(g, 1)
    g.authored_techniques['inherited'][book.id]['origin'] = 'previous'
    monkeypatch.setattr(author, 'enabled', lambda: False)
    assert not inherited_technique(g, 1)


@pytest.mark.parametrize('previous_ascension', [False, True])
def test_real_descent_submission_requires_prior_ascension_to_award(tmp_path, previous_ascension):
    from pathlib import Path
    from cultivation_life.engine import GameEngine
    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path)
    identity = engine.create_game('归乡验收', 'none', 'dao', 11001, preset_id='mahayana')['id']
    g = engine.store.load(identity)
    if previous_ascension:
        g.history.append(event('EVT_SPIRIT_CROSSING_003', 'entered_spirit_realm', world=['human', 'spirit']))
        engine.store.save(g)
    engine.manage_secret_art(identity, 'suppress', 'activate', 5, 9)
    shown = engine.cross_world(identity, 'human')
    assert ('衣锦还乡' in {r['name'] for r in shown['new_achievements']}) == previous_ascension
    saved = engine.store.load(identity)
    crossing = next(r for r in reversed(saved.history) if r.event_id == 'SYS_CROSS_WORLD')
    assert crossing.state_diff['mode'] == 'sealed_descent'
    assert '衣锦还乡' not in {r['name'] for r in engine.get_game(identity)['new_achievements']}
