"""NPC-only materials; shared ordinary-world supply policy, no game mutation."""
from functools import lru_cache
from .cultivation_coordinates import STARTS, END_RANK

SENSE_LIMITS = (STARTS[6]-1, STARTS[9]-1, END_RANK-1)

PATHS = {'dao': ('养元丹','淬玉髓','明神砂'), 'demonic': ('凝煞丹','炼煞髓','镇念晶'),
         'monster': ('血蕴丹','百骸髓','灵慧露'), 'ghost': ('养魄丹','冥骨髓','澄魂砂')}
AXES = ('cultivation','body','sense')
UPPER = dict(dao='celestial', demonic='asura', monster='nether', ghost='reincarnation')
TIERS = dict(human=1,demon=1,spirit=2,true_demon=2,monster_realm=2,
             phantom_underworld=2,hell=2,celestial=3,asura=3,nether=3,reincarnation=3)

@lru_cache(maxsize=1)
def definitions():
    rows = {f'npc_training_{path}_{axis}_{tier}':dict(
        id=f'npc_training_{path}_{axis}_{tier}',path=path,axis=axis,tier=tier,
        name=('凡品','灵品','上境')[tier-1]+names[i], price=(1,4,12)[tier-1])
        for path,names in PATHS.items() for i,axis in enumerate(AXES) for tier in (1,2,3)}
    for axis,name in dict(cultivation='蕴能芯',body='淬甲髓',sense='凝识枢',energy='能源晶').items():
        for tier in (1,2,3):
            identity=f'npc_training_puppet_{axis}_{tier}'
            rows[identity]=dict(id=identity,path='puppet',axis=axis,tier=tier,
                name=('凡品','灵品','上境')[tier-1]+name,price=(1,4,12)[tier-1])
            if axis=='energy':
                rank=(1,5,9)[tier-1]
                rows[identity].update(rank=rank,tier=1 if rank<=5 else 2 if rank<=8 else 3,name=f'{rank}阶傀儡能源晶')
    for rank in (2,3,4,6,7,8,10,11,12):
        identity=f'npc_training_puppet_energy_rank_{rank}'
        rows[identity]=dict(id=identity,path='puppet',axis='energy',rank=rank,
            tier=1 if rank<=4 else 2 if rank<=8 else 3,name=f'{rank}阶傀儡能源晶',price=rank*rank)
    for path,name in dict(dao='仙元露',demonic='煞元露',monster='妖元露',ghost='魂元露').items():
        identity=f'npc_training_{path}_conversion_3'
        rows[identity]=dict(id=identity,path=path,axis='conversion',tier=3,name=name,price=12)
    for path,name in dict(dao='悟域仙砂',demonic='凝域煞晶',monster='镇域妖髓',ghost='轮域魂砂').items():
        identity=f'npc_training_{path}_domain_3'
        rows[identity]=dict(id=identity,path=path,axis='domain',tier=3,name=name,price=12)
    for path,name in dict(dao='悟法仙笺',demonic='演法煞笺',monster='演法灵笺',ghost='悟法魂笺').items():
        for tier in (1,2,3):
            identity=f'npc_training_{path}_technique_{tier}'
            rows[identity]=dict(id=identity,path=path,axis='technique',tier=tier,name=('凡品','灵品','上境')[tier-1]+name,price=(1,4,12)[tier-1])
    for path,name in dict(dao='五光玉露',demonic='五蕴煞髓',monster='妖躯精粹',ghost='五法魂露').items():
        identity=f'npc_training_{path}_body_art_3'
        rows[identity]=dict(id=identity,path=path,axis='body_art',tier=3,name=name,price=12)
    return rows

def allowed(identity, world):
    row=definitions().get(identity)
    return bool(row and TIERS.get(world,0)>=row['tier']
                and (row['tier']<3 or row['path']=='puppet' or UPPER[row['path']]==world))

def build():
    items=[];goods=[]
    for row in definitions().values():
        effect={'cultivation':'培养修为，普通每轮1至3层，上境每轮1层。',
                'body':'培养肉身，普通每轮至多10层、高阶至多2层。',
                'sense':'培养神识，每轮至多8阶。','conversion':'转化元力，每轮最多20%，不恢复余额。',
                'technique':'研修NPC已掌握的功法，每轮一重，最高九重。',
                'body_art':'精修已解锁的肉身神通，每轮一重，上限十重。',
                'domain':'培养NPC原邻域／道统，每轮一阶，受修为上限限制，不补元力。',
                'energy':'可安装耐久100的能源；同阶耗5，低一／二阶耗20／60，低三阶不能驱动；高一／二／更多阶耗2／1／0.5。九阶起为仙级，凡阶傀儡无法承载。'}[row['axis']]
        items.append(dict(id=row['id'],name=row['name'],tags=['material','npc_training_material'],
            description='培养窗口专材，不可供玩家服用。'+effect+
            ('仅第三级普通界面可用。' if row['tier']==3 and row['path']=='puppet' else
             '仅对应道途上界可用。' if row['tier']==3 else '须在可承载本品阶的普通界面使用。')))
        for world in TIERS:
            if allowed(row['id'],world):
                goods.append(dict(world=world,kind='item',content_id=row['id'],
                    tier=(1,5,9)[row['tier']-1],price=row['price']))
    return items,goods

def shelf(game):
    """One finite offer per legal material per existing market refresh."""
    p=game.player
    return [dict(id=f'npc-{p.world}-{p.location_id}-{p.age}-{r["id"]}',kind='item',
        content_id=r['id'],name=r['name'],description='NPC专材 · 培养窗口使用',
        price=r['price'],tier=(1,5,9)[r['tier']-1],tier_name=('凡品','灵品','上境')[r['tier']-1],
        market_name='育才资材',world=p.world,location_id=p.location_id,
        rare_next_tier=False,sold=False,locked=False)
        for r in definitions().values() if allowed(r['id'],p.world)]
