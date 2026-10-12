"""Pure independent random streams for map bindings and five-node blueprints."""
import hashlib
import random

from .trial_site_schema import VERSION, PREFIX, REALM_ROWS, KINDS, SUBJECTS


def rng(seed, world, stream):
    return random.Random(f'{seed}:trial-site:v{VERSION}:{world}:{stream}')


def location_for(seed, world, candidates):
    if world not in REALM_ROWS or not candidates:
        raise ValueError('当前界面没有合法试境入口')
    rows = sorted(candidates)
    key = hashlib.sha256(f'{seed}:trial-site:v{VERSION}:{world}:location'.encode()).digest()
    return rows[int.from_bytes(key, 'big') % len(rows)]


def rank_for_floor(world, number):
    rows = REALM_ROWS[world]
    realm = rows[number - 1]
    repeated = [i + 1 for i, r in enumerate(rows) if r == realm]
    layers = {1: (5,), 2: (1, 9), 3: (1, 5, 9), 4: (1, 4, 7, 9), 5: (1, 3, 5, 7, 9)}
    return realm, layers[len(repeated)][repeated.index(number)]


def generate(seed, world, number, base_power, reward_pool):
    from .content_registry import WORLD_SYSTEMS
    boss_names = WORLD_SYSTEMS['trial_sites']['boss_names']
    realm, layer = rank_for_floor(world, number)
    situation = rng(seed, world, f'floor:{number}:situation')
    rewards = rng(seed, world, f'floor:{number}:rewards')
    pool = sorted(reward_pool, key=lambda row: (row['kind'], row['content_id']))
    if not pool:
        raise ValueError('本层缺少合法奖励目录')
    template = situation.randrange(3)
    subjects = situation.sample(SUBJECTS, 5)
    nodes = []
    for kind, subject in zip(KINDS, subjects):
        order = ['a', 'b', 'c']
        situation.shuffle(order)
        nodes.append(dict(kind=kind, subject=subject, variant=situation.randrange(4), order=order))
    identity = hashlib.sha256(f'{seed}:{world}:{number}:v{VERSION}'.encode()).hexdigest()[:16]
    return dict(id=f'{PREFIX}{world}_{number}_{identity}', number=number, realm=realm, layer=layer,
                base_power=base_power, boss_name=boss_names[template],
                template=template, nodes=nodes, rewards=[dict(rewards.choice(pool)) for _ in range(2)],
                index=0, delta=0., guard=True, bonus=False, supply=True, cooling=False,
                treasure=True, field=realm >= 9, history=[], attempts=0, revision=0,
                status='exploring', result=None, energy=1200. if realm >= 9 else 0.)
