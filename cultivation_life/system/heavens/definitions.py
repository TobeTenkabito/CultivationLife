"""Finite M1 action scope and framework definition validation."""
from dataclasses import dataclass, field, asdict

VIEWS = frozenset({'known', 'opportunities', 'tasks', 'history'})
ACTIONS = frozenset({'configure', 'watch', 'dismiss', 'observe', 'check_history',
                     'exchange', 'attune', 'maintain', 'correspond', 'resume', 'cancel'})


@dataclass(frozen=True, slots=True)
class ContactSite:
    id: str
    world: str
    location_id: str
    name: str
    visitor_name: str
    visitor_path: str
    spirit_root: str
    record_id: str
    evidence: tuple[str, str, str]
    findings: tuple[str, str, str]
    correspondence_years: int = 10
    correspondence_stones: int = 2500


CONTACT_SITES = (
    ContactSite('sea_echo', 'celestial', 'law_sea', '法则天海 · 潮汐回响', '观澜散人', 'dao', 'supreme_water', 'karma_city_old_copy',
        ('潮汐体察', '接引碑旧记', '因果天城合法抄录'),
        ('潮汐回响有稳定相位差，尚不能仅凭本地阵法解释。', '接引碑的两段旧记修正了“全部由本地阵法造成”的解释，可在本地应用。', '合法抄录支持因果天城旧节点与本地潮汐的联系；个人合作履约一次。')),
    ContactSite('asura_echo', 'asura', 'destruction_sea', '寂灭海 · 战律余响', '止戈客', 'demonic', 'mutated_thunder', 'celestial_seal_copy',
        ('战律余响', '古战阵铭', '仙界封阵抄录'),
        ('寂灭海的战律在无战事时仍有回响，不能把每次震动都解释为敌军来袭。', '古战阵铭中的两期静战记录说明，余响存在独立于兵力变化的周期。', '合法封阵抄录支持两界旧阵的响应联系；这份认识不授予军事通道或军队指挥权。')),
    ContactSite('nether_echo', 'nether', 'world_tree_crown', '界树天冠 · 万灵年轮', '听木叟', 'monster', 'supreme_wood', 'asura_growth_copy',
        ('万灵年轮', '树冠旧痕', '修罗古木抄录'),
        ('世界树年轮在灵潮平稳时仍出现共振，尚不能归因于血脉晋升。', '树冠旧痕保留两期异地响应，不同族类也能观察同一规律。', '合法古木抄录支持修罗界旧阵与年轮共振的联系；所得用于普通领悟，不增加血脉专属成果。')),
    ContactSite('reincarnation_echo', 'reincarnation', 'karma_city', '因果天城 · 三生回照', '照尘居士', 'ghost', 'supreme_water', 'nether_ring_copy',
        ('三生回照', '因果碑旧记', '幽冥年轮抄录'),
        ('回照留下不同年代的痕迹，却没有改变已经发生的生死。', '因果碑的两期旧记表明，所见是旧痕响应，不是时光倒流。', '合法年轮抄录支持幽冥旧节点与回照的联系；不会撤销死亡、复制人物或返还旧消耗。')),
)
SITE_IDS = frozenset(site.id for site in CONTACT_SITES)


def default_site(target_id):
    return next((site for site in CONTACT_SITES if site.id == target_id), None)


def validate_site(raw):
    if type(raw) is not dict or set(raw) != set(asdict(CONTACT_SITES[0])):
        raise ValueError('诸天联系地点字段无效')
    base = default_site(raw.get('id'))
    if not base or (raw['world'], raw['location_id'], raw['record_id']) != (base.world, base.location_id, base.record_id):
        raise ValueError('诸天联系必须引用各最高界面的实际地点与记录')
    for field_name in ('name', 'visitor_name', 'spirit_root'):
        if not isinstance(raw[field_name], str) or not 0 < len(raw[field_name]) <= 200:
            raise ValueError('诸天联系文本无效')
    if raw['visitor_path'] not in {'dao', 'demonic', 'monster', 'ghost'}:
        raise ValueError('诸天合作人物道途无效')
    for field_name in ('evidence', 'findings'):
        if not isinstance(raw[field_name], (list, tuple)) or len(raw[field_name]) != 3 or any(not isinstance(v, str) or not 0 < len(v) <= 1000 for v in raw[field_name]):
            raise ValueError('诸天联系证据定义无效')
    for field_name in ('correspondence_years', 'correspondence_stones'):
        if type(raw[field_name]) is not int or raw[field_name] <= 0:
            raise ValueError('诸天和平协作初值无效')


@dataclass(frozen=True, slots=True)
class SeaEchoDefinition:
    revision: int = 1
    period_years: int = 2000
    window_years: int = 1200
    extension_years: int = 600
    observe_years: int = 20
    history_years: int = 30
    exchange_years: int = 20
    maintain_years: int = 50
    history_stones: int = 10000
    exchange_stones: int = 20000
    maintain_stones: int = 20000


@dataclass(frozen=True, slots=True)
class HeavensDefinitions:
    milestone: str = 'M2-upper-worlds'
    generation_available: bool = False
    sea_echo: SeaEchoDefinition = field(default_factory=SeaEchoDefinition)
    contact_sites: tuple[ContactSite, ...] = CONTACT_SITES

    def site(self, target_id):
        return next((site for site in self.contact_sites if site.id == target_id), None)


def validate_echo_definition(raw: dict) -> None:
    keys = set(asdict(SeaEchoDefinition()))
    if type(raw) is not dict or set(raw) != keys:
        raise ValueError('法则天海定义字段无效')
    if any(type(value) is not int or value <= 0 for value in raw.values()):
        raise ValueError('法则天海初值必须为正整数')
    if raw['revision'] != 1 or not raw['window_years'] + raw['extension_years'] < raw['period_years']:
        raise ValueError('法则天海定义版本或周期无效')


def validate_framework(framework: dict, world_ids: set[str]) -> None:
    if type(framework) is not dict:
        raise ValueError('诸天框架配置必须为对象')
    if (framework.get('id') != 'heavens'
            or framework.get('kind') != 'cross_world_system'
            or type(framework.get('enabled')) is not bool):
        raise ValueError('诸天框架必须保持跨界系统类型及布尔开关')
    members = framework.get('member_worlds')
    if (not isinstance(members, list) or not all(isinstance(key, str) for key in members)
            or len(set(members)) != len(members) or not members
            or any(key not in world_ids for key in members) or 'heavens' in world_ids):
        raise ValueError('诸天框架成员必须引用真实界面，诸天不能作为角色界面')
    if 'sea_echo' in framework:
        validate_echo_definition(framework['sea_echo'])
    if 'contact_sites' in framework:
        rows = framework['contact_sites']
        if type(rows) is not list or len(rows) != 4:
            raise ValueError('诸天联系须覆盖四个最高界面')
        for row in rows:
            validate_site(row)
        if {row['id'] for row in rows} != SITE_IDS or {row['world'] for row in rows} != set(members):
            raise ValueError('诸天联系须唯一覆盖四个最高界面')
