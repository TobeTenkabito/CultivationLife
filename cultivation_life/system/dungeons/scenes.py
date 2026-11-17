"""Finite scene composition and structural variety, frozen at discovery."""
from collections import Counter
from . import prose

MECHANISMS = {
    'seal': ('fractured','resonant','volatile'),
    'hazard': ('fractured','resonant','volatile'),
    'core': ('volatile',), 'cache': ('cache',), 'trace': ('trail',),
    'contact': ('contact',), 'conflict': ('conflict',),
}
CLUES = {
    'fractured': '阵钉已从石座中松脱，灵流经过缺口时分成数股。',
    'resonant': '阵纹随护身灵光明灭，几道灵流正沿同一节律回旋。',
    'volatile': '积蓄的灵压冲撞石壁，阵眼深处传来接连的爆鸣。',
}
TACTICS = {
    'disarm': ('fractured', .08, 0., '顺着裂隙拆除阵钉'),
    'attune': ('resonant', .12, .25, '引导灵流平息阵势'),
}


def signature(node, roles):
    return (node['kind'],node.get('mechanism','legacy'),node['variant'],
            roles[node['actor']]['purpose'])


def history(game):
    return Counter(signature(n,s['roles']) for s in game.dungeon_state.get('instances',{}).values()
                   for n in s['nodes'])


def structure(rng, roles, used, core=False):
    candidates=[(kind,mechanism,variant,key) for kind in (('core',) if core else tuple(k for k in MECHANISMS if k!='core'))
                for mechanism in MECHANISMS[kind] for variant in range(8) for key in roles]
    scores=[used[(k,m,v,roles[a]['purpose'])] for k,m,v,a in candidates]
    least=min(scores)
    kind,mechanism,variant,actor=rng.choice([c for c,s in zip(candidates,scores) if s==least])
    used[(kind,mechanism,variant,roles[actor]['purpose'])]+=1
    return kind,mechanism,variant,actor


def compose(rng, location, theme, kind, direction, mechanism, used):
    parts=(prose.LANDMARKS[theme],prose.THEMED_DETAILS[theme],prose.THEMED_SENSES[theme],prose.EVENTS[kind])
    capacity=1
    for values in parts:capacity*=len(values)
    start=rng.randrange(capacity)
    # Every index names a distinct combination; no random retry or numeric suffix.
    for offset in range(min(capacity,len(used)+1)):
        index=(start+offset)%capacity;words=[]
        for values in parts:
            words.append(values[index%len(values)]);index//=len(values)
        text=f'{location}，{direction}侧的{words[0]}。'+''.join(words[1:])+CLUES.get(mechanism,'')
        if text not in used:
            used.add(text)
            return text
    raise ValueError(f'探索词库容量不足：{theme}/{kind}，请补充场景素材')


def tactic(node, choice):
    spec=TACTICS.get(choice)
    return spec if spec and node['kind'] in {'seal','hazard'} and node.get('mechanism')==spec[0] else None
