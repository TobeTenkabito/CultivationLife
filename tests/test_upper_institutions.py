import copy
import pytest

from test_upper_voisinages import upper, prepared
from cultivation_life.models import GameState
from cultivation_life.content_registry import CONTENT_DOCUMENTS
from cultivation_life.system.upper_institutions import (
    definition, account, public_institution, advance_time, votes, begin_work,
    finish_work, cultivation_discount,
)
from cultivation_life.system.upper_voisinage import quote


def join(e,g):
    g.player.location_id=definition(g)['location']
    e.store.save(g)
    e.upper_institution_action(g.id,'join')
    return e._load(g.id)


def test_membership_locality_and_pure_persistent_view(upper):
    e,g=upper
    before=copy.deepcopy(g.to_dict())
    assert public_institution(g)['available']
    assert g.to_dict()==before
    if g.player.location_id!=definition(g)['location']:
        with pytest.raises(ValueError,match='驻地'):
            e.upper_institution_action(g.id,'join')
    faction=g.player.faction_id
    g=join(e,g)
    assert g.player.faction_id==faction
    assert definition(g)['id'] in g.player.institution_affiliations
    assert g.sects[definition(g)['id']].kind=='institution'
    assert GameState.from_dict(g.to_dict()).upper_institutions==g.upper_institutions
    before=copy.deepcopy(g.to_dict())
    e.get_game(g.id)
    assert e._load(g.id).upper_institutions==g.upper_institutions
    g.player.world='spirit'
    assert not public_institution(g)['available']
    advance_time(g,1000,100)
    assert g.upper_institutions==before['upper_institutions']
    e.store.save(g)
    with pytest.raises(ValueError):e.upper_institution_action(g.id,'claim')


def test_fractional_time_cannot_mint_stipends_or_double_claim(upper):
    e,g=upper;g=join(e,g);state=account(g)
    for _ in range(99):advance_time(g,1,100)
    assert state['unit']==0
    advance_time(g,1,100)
    assert state['unit']==1
    assert state['treasury']==2000000+600000-10000
    e.store.save(g)
    e.upper_institution_action(g.id,'accept')
    g=e._load(g.id);begin_work(g)
    finish_work(g,'rest',100)
    assert account(g)['job']['progress']==0
    finish_work(g,'institution_work',40)
    e.store.save(g)
    with pytest.raises(ValueError,match='尚未完成'):e.upper_institution_action(g.id,'claim')
    finish_work(g,'institution_work',60)
    e.store.save(g)
    e.upper_institution_action(g.id,'claim')
    g=e._load(g.id)
    assert account(g)['merit']==100 and account(g)['earned']==100
    before=copy.deepcopy(g.upper_institutions)
    with pytest.raises(ValueError):e.upper_institution_action(g.id,'claim')
    assert e._load(g.id).upper_institutions==before


def test_policies_materials_and_currency_are_real_and_atomic(upper):
    e,g=upper;g=join(e,g);state=account(g)
    expected=.2 if g.player.world=='reincarnation' else .15
    assert cultivation_discount(g)==expected
    assert quote(g.player,1,g)['stones'] < quote(g.player,1)['stones']
    state.update(merit=800,earned=800)
    e.store.save(g)
    before=len(g.player.crafting_materials)
    e.upper_institution_action(g.id,'material')
    g=e._load(g.id)
    assert len(g.player.crafting_materials)==before+1
    assert account(g)['merit']==200 and account(g)['earned']==800
    e.upper_institution_action(g.id,'stones')
    g=e._load(g.id)
    assert account(g)['merit']==100 and account(g)['treasury']==1750000
    before=copy.deepcopy(g.to_dict())
    with pytest.raises(ValueError):e.upper_institution_action(g.id,'material')
    assert e._load(g.id).upper_institutions==before['upper_institutions']


def test_monarchy_oligarchy_theocracy_different_rules(upper):
    e,g=upper;g=join(e,g);state=account(g)
    state.update(merit=2000,earned=2000,regard=100)
    g.player.realm_index=11
    e.store.save(g)
    if g.player.world=='nether':
        for _ in range(3):e.upper_institution_action(g.id,'lobby','0')
        e.upper_institution_action(g.id,'patronage')
        g=e._load(g.id);state=account(g)
        assert state['seat_active']
        # Two supporters (5+1) cannot beat a weighted majority; buy a 4-weight ally.
        assert sum(v['weight'] for v in votes(g,'prosper',player=True) if v['yes'])==6
        e.upper_institution_action(g.id,'lobby','1')
        e.upper_institution_action(g.id,'lobby','1')
        g=e._load(g.id);state=account(g)
        assert sum(v['weight'] for v in votes(g,'prosper',player=True) if v['yes'])==10
        before=state['treasury']
        e.upper_institution_action(g.id,'policy','prosper')
        g=e._load(g.id);state=account(g)
        assert state['policy']=='prosper' and state['treasury']==before-120000
        with pytest.raises(ValueError):e.upper_institution_action(g.id,'policy','war')
        advance_time(g,1400,100)
        assert state['seat_active']  # no fixed-term election
        state['support'][state['bloc']]=49
        advance_time(g,100,100)
        assert not state['seat_active']
        assert not g.pending_event
        e.store.save(g)
        with pytest.raises(ValueError,match='代言'):e.upper_institution_action(g.id,'policy','war')
    else:
        for _ in range(2):e.upper_institution_action(g.id,'promote')
        e.upper_institution_action(g.id,'policy','war')
        g=e._load(g.id);state=account(g)
        assert state['rank']==2 and state['policy']=='war'
        if g.player.world=='asura':
            advance_time(g,100,100)
            assert state['obligation']
            advance_time(g,500,100)
            assert state['regard']==85
        else:
            e.upper_institution_action(g.id,'vow')
            e.upper_institution_action(g.id,'rite')
            e.upper_institution_action(g.id,'accept')
            g=e._load(g.id);state=account(g)
            assert state['job']['reward']==162
            assert state['obligation'] and state['blessing_until']==4
            with pytest.raises(ValueError):e.upper_institution_action(g.id,'rite')
            advance_time(g,500,100)
            assert state['regard']==85 and state['obligation'] is None


def test_direct_work_guards_and_actual_advancement_hook(upper,monkeypatch):
    e,g=upper;g=join(e,g)
    with pytest.raises(ValueError):e.advance(g.id,'institution_work',1)
    e.upper_institution_action(g.id,'accept')
    monkeypatch.setattr(e,'_advance_world_year',lambda *args,**kw:True)
    e.upper_institution_action(g.id,'work')
    g=e._load(g.id)
    assert account(g)['unit']==1
    assert account(g)['job']['progress']==100
    assert account(g)['job']['years']==100


def test_empty_council_does_not_vote_or_charge(upper):
    e,g=upper;g=join(e,g);state=account(g)
    for n in g.sects[definition(g)['id']].npcs:n.alive=False
    advance_time(g,400,100)
    assert state['policy']=='study'
    if g.player.world=='nether':
        assert not any(v['yes'] for v in votes(g,'war'))


def test_base_upper_map_connectivity_and_nonadjacent_arrays():
    maps=CONTENT_DOCUMENTS['maps.json']['worlds']
    for world,minimum in [('asura',23),('nether',27),('reincarnation',28)]:
        w=maps[world];loc={r['id']:r for r in w['locations']};edges={k:set() for k in loc}
        for r in w['routes']:edges[r['from']].add(r['to']);edges[r['to']].add(r['from'])
        seen={w['default']};todo=list(seen)
        while todo:
            for k in edges[todo.pop()]:
                if k not in seen:seen.add(k);todo.append(k)
        assert len(loc)>=minimum and seen==set(loc)
        arrays={k for k,v in loc.items() if v.get('teleport_array')}
        assert len(arrays)>=11
        assert not any(edges[k]&arrays for k in arrays)


def test_native_upper_quick_starts(upper):
    e,g=upper
    world=g.player.world
    view=e.create_game('三界开局','supreme_metal','dao',1522,preset_id=world+'_upper')
    g=e._load(view['id']);p=g.player
    assert p.world==world and p.realm_index==9 and p.layer==1
    assert p.path=={'asura':'demonic','nether':'monster','reincarnation':'ghost'}[world]
    assert p.location_id==definition(g)['location']
    assert p.technique.id==f'TECH_{world.upper()}_9_MAIN'
    assert p.body_technique.id==f'TECH_{world.upper()}_9_BODY'
    assert p.divine_sense_technique.id==f'TECH_{world.upper()}_9_SENSE'
    assert view['upper_voisinages']['rows'][0]['level']==1
    assert view['upper_voisinages']['rows'][0]['active']
    assert view['aperture']['current']==600
    assert not view['player']['opportunity_unbounded']
    assert not account(g)['joined']
    if world=='nether':
        from cultivation_life.content_registry import MONSTER_EVOLUTIONS
        from cultivation_life.system.monster_bloodline_system import evolution_candidates
        assert MONSTER_EVOLUTIONS[p.monster_evolution_id]['realm_index']==9
        assert any(row['id']!='__stable__' for row in evolution_candidates(p))
