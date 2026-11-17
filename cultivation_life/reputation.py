"""Independent punitive infamy and factual renown; no catalog or model dependency."""
import math
from .cultivation_coordinates import rank_for, body_rank


def decode_player(data):
    """Schema-12 field-name boundary. Never mutate the source document."""
    for old, new in [('fame', 'infamy'), ('fame_by_world', 'infamy_by_scope')]:
        if old in data:
            if new in data and data[new] != data[old]:
                raise ValueError('旧威名与新凶名字段冲突，保留原存档')
            data[new] = data.pop(old)
    value = data.get('infamy', 0)
    if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
        raise ValueError('凶名数值无效')
    scopes = data.get('infamy_by_scope', {})
    if not isinstance(scopes, dict) or any(not isinstance(k, str) or type(v) not in (float, int)
            or not math.isfinite(v) or v < 0 for k, v in scopes.items()):
        raise ValueError('凶名作用域无效')
    records = data.get('renown_records', {})
    if not isinstance(records, dict) or len(records) > 20000:
        raise ValueError('威名事迹记录无效')
    for key, row in records.items():
        if (not isinstance(key, str) or not isinstance(row, dict)
                or set(row) != {'scope', 'amount', 'reason'} or not isinstance(row['scope'], str)
                or not isinstance(row['reason'], str) or type(row['amount']) not in (int, float)
                or not math.isfinite(row['amount']) or abs(row['amount']) > 1000):
            raise ValueError('威名事迹字段无效')
    return data


def true_rank(player):
    rows = [(player.realm_index, player.layer)]
    for key in ('sealed_cultivation', 'cultivation_suppression'):
        row = getattr(player, key, None) or {}
        rows.append((int(row.get('realm_index', 0)), int(row.get('layer', 1))))
    return max(rows, key=lambda row: rank_for(*row))


def assess(player, *, scope=None, visible=False):
    # A stranger sees manifested strength, never a secret true-rank aggregate.
    realm, layer = (player.realm_index, player.layer) if visible else true_rank(player)
    strength = round(rank_for(realm, layer) * 4.0, 1)
    body = body_rank(player.body_training, player.immortal_body.get('level', 0)) * .35
    sense = player.divine_sense_rank * .2
    arts = sum(min(30., math.log1p(max(0, v))*2) for v in player.art_experience.values())
    equipped = [player.technique, player.support_technique, *player.combat_techniques]
    mastery = sum(t.level * min(12,t.grade) * .25 for t in {t.id:t for t in equipped if t}.values())
    if visible:body=sense=mastery=0  # Private cultivation/loadout is not public reputation.
    strength = round(strength+body+sense+mastery,1)
    place = scope or getattr(player, '_renown_scope', player.world)
    deeds = sum(r['amount'] for r in player.renown_records.values() if r['scope'] == place
        and (not visible or r['reason']!='探境所得'))
    return dict(value=round(max(0, strength + arts + deeds), 1), strength=strength,
                arts=round(arts,1),deeds=round(deeds, 1), scope=place)


def record(player, identity, amount, reason, *, scope=None):
    if identity in player.renown_records:
        return False
    if len(player.renown_records)>=20000:raise ValueError('威名事迹记录已达上限')
    if type(amount) not in (int, float) or not math.isfinite(amount) or abs(amount) > 1000:
        raise ValueError('威名事迹增量无效')
    player.renown_records[identity] = dict(scope=scope or getattr(player, '_renown_scope', player.world), amount=amount, reason=reason)
    return True


def bind_scope(game):
    world=game.player.world
    instance=game.spatial_state.get('current') if world in {'rift','lost'} else None
    game.player._renown_scope=f'{world}:{instance}' if instance else world


def decode_pending(value):
    """Only the renamed punitive vocabulary in already-stored effects/conditions."""
    import copy
    value=copy.deepcopy(value)
    def walk(row):
        if isinstance(row,list):
            for entry in row:walk(entry)
        elif isinstance(row,dict):
            if row.get('type')=='add_fame':row['type']='add_infamy'
            if row.get('path')=='player.fame':row['path']='player.infamy'
            for entry in row.values():walk(entry)
    walk(value)
    return value
