"""Small instance-local societies; people remain references to the NPC registry."""
import copy

from ..spatial_people import people
from ..models import Technique
from ..rules import learn_technique


def families(scene):
    # Deterministic projection also supports old scenes without consuming RNG.
    return scene.get('families', [dict(id=scene['id'] + f'_family_{i}',
        name=scene['name'][:2] + surname + '氏家族', location_id=scene['locations'][i + 1]['id'],
        member_ids=scene.get('npc_ids', [])[i::2]) for i, surname in enumerate(('林', '陆'))])


def public(game, scene):
    if scene.get('kind') != 'lost':
        return None
    local = people(game, scene)
    def rows(kind, source):
        return [dict(copy.deepcopy(row), kind=kind,
                     members=[npc.to_dict() for npc in local if npc.alive and
                              (npc.faction_id == row['id'] if kind == 'sect' else npc.id in row['member_ids'])],
                     joined=scene.get('joined_' + kind) == row['id'],
                     here=scene['location_id'] == row['location_id']) for row in source]
    return dict(sects=rows('sect', scene['sects']), families=rows('family', families(scene)))


def act(game, scene, action, target):
    if scene.get('kind') != 'lost':
        raise ValueError('只有失落界面拥有本地宗族')
    kind = 'family' if 'family' in action else 'sect'
    source = families(scene) if kind == 'family' else scene['sects']
    row = next((r for r in source if r['id'] == target), None)
    if not row:
        raise ValueError('该宗族不在当前失落界面')
    key = 'joined_' + kind
    members = next(r['members'] for r in public(game, scene)['families' if kind == 'family' else 'sects'] if r['id'] == target)
    if action.startswith('leave_'):
        if scene.get(key) != target:
            raise ValueError('尚未加入该宗族')
        scene[key] = None
        return f"辞别{row['name']}，保留外界身份。"
    if scene['location_id'] != row['location_id'] or not members:
        raise ValueError('须前往有在世成员的宗族驻地')
    if action.startswith('join_'):
        if scene.get(key):
            raise ValueError('请先退出当前本地宗族')
        scene[key] = target
        if kind == 'family':
            scene.setdefault('families', copy.deepcopy(source))
        return f"加入{row['name']}，身份仅在此失落界面生效。"
    if scene.get(key) != target:
        raise ValueError('须先加入此宗族')
    if action.startswith('study_'):
        index = source.index(row) % len(scene['techniques'])
        book = Technique(**copy.deepcopy(scene['techniques'][index]))
        if any(t.id == book.id for t in game.player.known_techniques):
            raise ValueError('已经学过这部本界传承')
        learn_technique(game.player, book)
        return f"向{row['name']}请教，习得本界传承{book.name}。"
    raise ValueError('未知宗族事务')
