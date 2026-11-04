"""Ranked fuels, explicit domain progression, original identities and replay facts."""
import copy
from dataclasses import replace
import pytest
from test_npc_development import game
from test_puppet_energy_supply import battle
from cultivation_life.rules import add_item
from cultivation_life.system import puppet_energy as energy
from cultivation_life.system.npc_development import service,presentation
from cultivation_life.system.doctrine.state import ensure
from cultivation_life.system.doctrine.provider import battle_sources


def fuel(rank):
    from cultivation_life.npc_development_content import definitions
    return next(r['id'] for r in definitions().values() if r.get('rank')==rank)


def test_all_energy_rank_pairs_and_immortal_boundary():
    for realm in range(1,13):
        for rank in range(1,13):
            use=energy.operation(dict(realm_index=realm,energy_source_id=fuel(rank)))
            compatible=not(rank>=9>realm or realm-rank>=3)
            assert use['compatible']==compatible
            assert energy.force_tier({'energy_source_id':fuel(rank)})==(2 if rank>=9 else 1)
            if compatible:
                gap=realm-rank
                expected={2:60,1:20,0:5,-1:2,-2:1}.get(gap,.5)
                assert use['cost']==expected


@pytest.mark.parametrize('realm,rank,durability,expected',[(8,7,100,80),(8,6,100,40),(8,5,100,100),
    (7,8,100,98),(6,8,100,99),(4,8,100,99.5),(8,9,100,100),(9,9,100,95),(10,9,100,80),(12,9,100,100)])
def test_real_attack_uses_grade_cost_or_stops(realm,rank,durability,expected):
    use=energy.operation(dict(realm_index=realm,energy_source_id=fuel(rank)))
    b=battle(high=realm>=9,grade=2 if rank>=9 else 1,charge=durability,supply=False)
    s=b.units['puppet-0'];s.unit=replace(s.unit,capabilities=replace(s.unit.capabilities,
        operating_cost=use['cost'],operating_compatible=use['compatible']))
    b.ordinary_damage(.1,0)
    assert s.operating_energy==expected
    assert ('puppet-0' in b.report()['ordinary_attacks'])==use['compatible']
    assert b.units['player'].current==20 and b.units['player'].mana_current==20


def test_install_rejects_overload_and_excessive_gap_without_payment(game):
    a=dict(id='p',name='甲',type='mechanical',realm_index=8,layer=1,alive=True,operating_energy=50)
    game.player.puppets=[a];game.player.world='celestial'
    for rank in (5,9):
        add_item(game.player,fuel(rank),1);before=copy.deepcopy(game.to_dict())
        with pytest.raises(ValueError):service.charge(game,'puppet','p','bag:'+fuel(rank))
        assert game.to_dict()==before


@pytest.mark.parametrize('path,world',[('dao','celestial'),('demonic','asura'),('monster','nether'),('ghost','reincarnation')])
def test_domains_use_original_records_and_reach_actual_battle(game,path,world):
    n=game.world_npcs['student'];n.world=game.player.world=world;n.path=path;n.realm_index=9;n.layer=8
    n.transcendence=dict(conversion=1.,capacity=1000.,current=123.,force_tier=2,attack_cost=10.)
    if world=='celestial':ensure(game)
    material=f'npc_training_{path}_domain_3';add_item(game.player,material,20)
    before=copy.deepcopy(game.to_dict());q=service.quote(game,'npc',n.id,'domain','material',10)
    assert game.to_dict()==before and q['opportunity']==0
    service.apply(game,'npc',n.id,'domain','material',10)
    assert n.transcendence['current']==123
    assert n.world==world and game.player.age==before['player']['age']
    value=battle_sources(game,{n.id:n})[n.id]
    assert value.voisinages
    from cultivation_life.system.combat.contracts import resolve_source,Combatant
    from cultivation_life.system.combat.voisinages import VoisinageBattle
    caps=resolve_source(n.transcendence,{},value)
    fight=VoisinageBattle([Combatant(n.id,n.name,'player',1000,replace(caps,current=caps.capacity)),
        Combatant('enemy','对手','enemy',1000)])
    fight.begin_round(1,player_condition=1,enemy_condition=1,player_mp=1,enemy_mp=1)
    assert any(f['owner']==n.id for f in fight.report()['fields'])
    assert game.player.disciples[0].person is n
    after=copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError):service.apply(game,'npc',n.id,'domain','material')
    assert game.to_dict()==after
    n.realm_index=10
    service.apply(game,'npc',n.id,'domain','material',1)
    assert n.transcendence['current']==123


@pytest.mark.parametrize('problem',['world','unconverted','puppet','busy','teacher','missing'])
def test_domain_rejections_do_not_spend(game,problem):
    n=game.world_npcs['student'];n.world=game.player.world='celestial';n.realm_index=9
    n.transcendence=dict(conversion=1,capacity=1000,current=17)
    ensure(game);add_item(game.player,'npc_training_dao_domain_3',5)
    kind='npc';identity=n.id;method='material'
    if problem=='world':game.player.world=n.world='spirit'
    if problem=='unconverted':n.transcendence['conversion']=.8
    if problem=='busy':game.pending_event={'id':'event'}
    if problem=='teacher':method='infuse'
    if problem=='missing':game.player.inventory=[]
    if problem=='puppet':
        game.player.puppets=[dict(id='p',type='mechanical',realm_index=9,layer=1,alive=True)]
        kind='puppet';identity='p'
    before=copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError):service.apply(game,kind,identity,'domain',method)
    assert game.to_dict()==before


def test_prisoner_portrait_preserves_person_and_growth(game):
    n=game.world_npcs['student'];n.world=game.player.world='asura';n.path='demonic';n.realm_index=9
    n.transcendence=dict(conversion=1,capacity=1000,current=17)
    game.player.prisoners.append(game.detain_person({'id':n.id,'combat_power':100}))
    add_item(game.player,'npc_training_demonic_domain_3',1)
    before=copy.deepcopy(game.to_dict());row=next(r for r in presentation.public(game)['targets'] if r['id']==n.id)
    assert row['portrait']['gender']==n.gender and row['portrait']['restraint']
    assert game.to_dict()==before
    service.apply(game,'prisoner',n.id,'domain','material')
    assert n.transcendence['world_voisinages']['asura']['levels']
