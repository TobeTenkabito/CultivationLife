"""Read-only personal soul view; never charges, rolls or advances clocks."""
import copy
from ..soul_secret_content import acquisition_hint
from ..content_registry import PATH_NAMES, REALMS
from ..soul_rules import SECRETS, PATH_QI, wandering, body_cap, soul_cap, assimilation_cost, rebellion_chance
from .soul_lifecycle import second_person, second_age, second_lifespan
from .soul_actions import blocked, resistance_blocked, conversion_quote, conversion_token, captive
from .npc_techniques import public as public_books
from .second_nascent import power


def public(game):
    p = game.player
    state = p.nascent_state
    npc = second_person(game)
    captives = []
    for row in p.prisoners:
        try:
            candidate = captive(game, row['id'])
        except ValueError:
            continue
        if candidate.realm_index >= 4:
            captives.append(dict(id=candidate.id, name=candidate.name, realm=candidate.realm_index))
    return dict(revision=state.get('revision', 0), blocked=bool(blocked(game)),
        can_resist=state.get('crisis') == 'possession' and not resistance_blocked(game),
        body=dict(current=p.body_energy, maximum=body_cap(p)),
        soul=dict(current=p.soul_energy, maximum=soul_cap(p)),
        mode='神游' if wandering(p) else '普通', spirit=copy.deepcopy(p.spirit_state),
        possessed=bool(p.ghost_host_body),
        remaining=None if p.path == 'ghost' or not wandering(p) else max(0, p.spirit_state['deadline']-p.age),
        leave_unlocked=p.realm_index >= 4,
        can_leave=p.realm_index >= 4 and not wandering(p) and not p.ghost_host_body,
        can_refine=p.realm_index >= 4,
        stagnant=bool(state.get('stagnant')), crisis=state.get('crisis'),
        resistance_chance=min(.9, .35+p.divine_sense_rank*.025),
        secrets=[dict(id=k, name=v[0], rank=v[1], realm_name=REALMS[v[1]].name, acquisition_hint=acquisition_hint(k), known=k in state.get('known', []), eligible=p.realm_index>=v[1]) for k,v in SECRETS.items()],
        conversions=[dict(id=k, name=PATH_NAMES.get(k,k), learned='path_'+k in state.get('known', []),
            has_book=any(t.path==k for t in p.known_techniques), quote=conversion_token(game,k), **conversion_quote(p,k)) for k in PATH_QI if k!=p.path],
        refining=copy.deepcopy(state.get('refining')),
        captives=captives,
        second=(dict(**copy.deepcopy(state['second']),name=npc.name,realm=REALMS[npc.realm_index].name,
            age=second_age(game,npc),lifespan=second_lifespan(npc),
            next_rebellion_chance=rebellion_chance(max(0.,state['second'].get('control',100.)-2)),
            layer=npc.layer,power=power(game),cost=assimilation_cost(npc.realm_index),
            books=public_books(game,npc),slots={'main':npc.main_technique_id,**npc.technique_slots}) if npc else None),
        equipment=[dict(id=i.id,name=i.name) for i in p.inventory if i.combat_bonus>0 and not i.crafted_artifact_id],
        techniques=[dict(id=t.id,name=t.name,level=t.level) for t in p.known_techniques])
