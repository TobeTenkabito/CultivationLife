"""Owned clone assets; authored grants never duplicate a person or party member."""
from ..puppet_state import usable
from ..npc_development_content import TIERS
from .puppet_energy import can_deploy, current

from ..puppet_state import DANCE_IDS, cultivation_cap


def dance_claim_reason(player):
    if any(a.get('id') in DANCE_IDS or a.get('source_secret')=='manual_demon_dance' for a in player.puppets):
        return '天魔乱舞分身已凝成，不能重复领取'
    return ''


def grant_dance_pair(player):
    """Only called inside the secret-art copy/pay/save transaction."""
    from ..content_registry import REALMS
    from ..cultivation_coordinates import rank_for
    if reason:=dance_claim_reason(player):raise ValueError(reason)
    for identity,name in zip(DANCE_IDS,('岚影分身','魔影分身')):
        player.puppets.append(dict(id=identity,name=name,type='clone',source_secret='manual_demon_dance',
            path='demonic',race='human',gender=player.gender,age=0,spirit_root='mutated_wind',
            realm_index=4,layer=1,combat_power=round(REALMS[4].base_power*.35,1),
            body_training=0,divine_sense_rank=rank_for(4,1),alive=True,durability=100.,
            operating_energy=0.,energy_source_id=None,main_technique_id=None,breakthrough_bonus=0.))


def units(game, *, trial=False):
    from .combat_system import BattleUnit
    from .combat_adapter import persistent_owner
    from collections import Counter
    p=game.player
    from ..soul_rules import wandering
    if not p.alive or wandering(p) or p.sealed_cultivation or p.cultivation_suppression:
        return []
    tier=TIERS.get(p.world)
    if tier is None or trial and (tier!=3 or p.realm_index<9):
        return []
    result=[];seen=set()
    counts=Counter(str(a.get('id','')) for a in p.puppets)
    for asset in p.puppets:
        identity=asset.get('id')
        rank=int(asset.get('realm_index',0))
        if (asset.get('type')!='clone' or not isinstance(identity,str) or not identity
                or identity=='player' or identity.startswith('enemy-') or identity in seen or counts[identity]!=1
                or not usable(asset,game) or not can_deploy(p,asset)
                or not 1<=rank<=min({1:5,2:8,3:12}[tier],cultivation_cap(asset)) or trial and rank<9):
            continue
        if persistent_owner(game,identity) is not asset:continue
        seen.add(identity)
        integrity=max(0.,min(1.,float(asset.get('durability',100))/100))
        power=max(0.,float(asset.get('combat_power',0)))
        if integrity<=.05 or power<=0:continue
        result.append(BattleUnit(identity,str(asset.get('name','分身')),'clone',power,rank,
                                str(asset.get('path',p.path)),integrity,'durability'))
    return result


def freeze_stats(state, clones):
    """Mirror foes have already been built from the player's own attributes."""
    if not clones:return
    from .combat_system import PlayerCombatSystem
    state['clone_stats']={u.id:PlayerCombatSystem._aggregate_stats([u],terrain_tags=['开阔']) for u in clones}


def commit(game,battle,state):
    owners={a['id']:a for a in game.player.puppets if a.get('type')=='clone'}
    for identity in state.get('clone_stats',{}):
        asset=owners.get(identity);unit=battle.units.get(identity)
        if asset is None or unit is None:continue
        if unit.operating_energy is not None:
            asset['operating_energy']=min(current(asset),max(0.,unit.operating_energy))
        asset['durability']=min(float(asset.get('durability',100)),max(0.,min(unit.body,unit.vitality)*100))
        if unit.body<=0 or unit.vitality<=.05:
            asset['alive']=False


def roster(battle,state):
    return [dict(id=s.unit.id,name=s.unit.name,power=s.unit.power,
                 kind='clone' if s.unit.id in state.get('clone_stats',{}) else 'player',
                 kind_name='分身' if s.unit.id in state.get('clone_stats',{}) else '玩家')
            for s in battle.units.values() if s.unit.side=='player']
