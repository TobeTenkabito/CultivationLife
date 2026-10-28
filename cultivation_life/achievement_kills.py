"""Bounded historical evidence from the authoritative player kill settlement."""
from .models import HistoryRecord
from .relationship_records import find_person


KEY = 'ghost_non_ghost_kills'
EVENT = 'SYS_GHOST_CULTIVATOR_KILL'


def record(game, victim):
    player = game.player
    if (player.path != 'ghost' or victim.get('actor', 'player') != 'player'
            or player.milestones.get(KEY, 0) >= 100
            or victim.get('kind') in {'artifact', 'formation', 'environment', 'mechanical', 'corpse', 'beast'}):
        return
    identity = str(victim.get('npc_id') or victim.get('id') or '')
    person = find_person(game, identity, include_inactive=True) if identity else None
    cached = next((r.get('npc', {}) for r in game.encounter_npc_cache if r.get('id') == identity), {}) if identity else {}
    path = person.path if person else cached.get('path', victim.get('path'))
    realm = person.realm_index if person else cached.get('realm_index', victim.get('realm_index', 0))
    if path not in {'dao', 'demonic', 'monster', 'buddhist', 'confucian'} or realm < 1:
        return
    if identity and any(r.event_id == EVENT and r.choice_id == identity for r in game.history):
        return
    count = int(player.milestones.get(KEY, 0)) + 1
    player.milestones[KEY] = count
    game.history.append(HistoryRecord(EVENT, 1, player.age, '百鬼夜行', identity, 'killed',
        f'以鬼修之身击杀非鬼修修士，累计 {count}/100。',
        {'player_path': 'ghost', 'victim_path': path, 'victim_realm': realm, 'count': count},
        ['system', 'achievement']))
