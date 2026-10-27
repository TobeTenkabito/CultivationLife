"""Read-only personal soul view; never charges, rolls or advances clocks."""
import copy
from ..content_registry import PATH_NAMES, REALMS
from ..soul_rules import SECRETS, PATH_QI, wandering, body_cap, soul_cap, assimilation_cost
from .soul_lifecycle import second_person
from .soul_actions import blocked, conversion_quote
from .npc_techniques import public as public_books
from .second_nascent import power


def public(game):
    p = game.player
    state = p.nascent_state
    npc = second_person(game)
    return dict(revision=state.get('revision', 0), blocked=bool(blocked(game)),
        body=dict(current=p.body_energy, maximum=body_cap(p)),
        soul=dict(current=p.soul_energy, maximum=soul_cap(p)),
        mode='神游' if wandering(p) else '普通', spirit=copy.deepcopy(p.spirit_state),
        possessed=bool(p.ghost_host_body),
        remaining=None if p.path == 'ghost' or not wandering(p) else max(0, p.spirit_state['deadline']-p.age),
        can_leave=(p.realm_index >= 4 or p.path == 'ghost') and not wandering(p) and not p.ghost_host_body,
        stagnant=bool(state.get('stagnant')), crisis=state.get('crisis'),
        resistance_chance=min(.9, .35+p.divine_sense_rank*.025),
        secrets=[dict(id=k, name=v[0], rank=v[1], realm_name=REALMS[v[1]].name, price=v[2], known=k in state.get('known', []), eligible=p.realm_index>=v[1]) for k,v in SECRETS.items()],
        conversions=[dict(id=k, name=PATH_NAMES.get(k,k), learned='path_'+k in state.get('known', []),
            has_book=any(t.path==k for t in p.known_techniques), **conversion_quote(p,k)) for k in PATH_QI if k!=p.path],
        refining=copy.deepcopy(state.get('refining')),
        captives=[dict(id=r['id'],name=r.get('name'),realm=r.get('realm_index')) for r in p.prisoners if r.get('alive',True) and r.get('realm_index',0)>=4],
        second=(dict(**copy.deepcopy(state['second']),name=npc.name,realm=REALMS[npc.realm_index].name,
            layer=npc.layer,power=power(game),cost=assimilation_cost(npc.realm_index),
            books=public_books(game,npc),slots={'main':npc.main_technique_id,**npc.technique_slots}) if npc else None),
        equipment=[dict(id=i.id,name=i.name) for i in p.inventory if i.combat_bonus>0 and not i.crafted_artifact_id],
        techniques=[dict(id=t.id,name=t.name,level=t.level) for t in p.known_techniques])
