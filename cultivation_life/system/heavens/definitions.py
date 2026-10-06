"""Finite M1 action scope and framework definition validation."""
from dataclasses import dataclass, field, asdict
from .frontier_definitions import FRONTIER_ACTIONS
from .campaign_definitions import CAMPAIGN_ACTIONS

VIEWS = frozenset({'known', 'opportunities', 'tasks', 'history'})
MIRROR_ID = 'mirror_field'
MIRROR_ACTIONS = frozenset({'mirror_enter', 'mirror_leave', 'mirror_probe', 'mirror_decipher', 'mirror_isolate', 'mirror_assault', 'mirror_repair', 'mirror_release'})
RUINS_ID = 'causal_ruins'
RUINS_ACTIONS = frozenset('ruins_' + name for name in ('enter', 'leave', 'observe', 'verify', 'read', 'take', 'replace', 'erase', 'contact', 'return'))
VISIT_ACTIONS = frozenset({'visit_depart', 'visit_study', 'visit_return'})
UPKEEP_ACTIONS = frozenset({'upkeep_start', 'upkeep_cancel'})
SURVEY_ACTIONS = frozenset({'survey_start', 'survey_recall', 'survey_share', 'survey_wait'})
MIGRATION_ACTIONS = frozenset({'migration_start', 'migration_cancel'})
FREIGHT_ACTIONS = frozenset({'freight_start', 'freight_cancel', 'freight_collect'})
MISSION_ACTIONS = frozenset({'mission_start', 'mission_recall', 'mission_wait'})
VISIT_DESTINATIONS = {'sea_echo': 'reincarnation_echo', 'asura_echo': 'sea_echo',
                      'nether_echo': 'asura_echo', 'reincarnation_echo': 'nether_echo'}
ACTIONS = frozenset({'configure', 'watch', 'dismiss', 'observe', 'check_history',
                     'exchange', 'attune', 'maintain', 'correspond', 'resume', 'cancel', 'omen_study'}) | MIRROR_ACTIONS | RUINS_ACTIONS | VISIT_ACTIONS | MISSION_ACTIONS | FREIGHT_ACTIONS | MIGRATION_ACTIONS | SURVEY_ACTIONS | UPKEEP_ACTIONS | FRONTIER_ACTIONS | CAMPAIGN_ACTIONS


@dataclass(frozen=True, slots=True)
class OmenDefinition:
    id: str
    name: str
    location_id: str
    location_name: str
    glimpse: str
    finding: str
    anomaly_id: str
    world: str = 'human'
    revision: int = 1
    study_years: int = 2
    cooldown_years: int = 200
    lifetime_years: int = 600


OMENS = (
    OmenDefinition('sand_glimmer', '沙中重影', 'muling_desert', '穆陵沙漠',
        '沙粒上偶有错开的双重倒影，静止的石片也映出微光。尚不知其来历，可以留在当地对照。',
        '对照日影与旧石后，确认重影来自此地一处稳定镜纹，而非寻常风沙。元婴后可亲自感知入口；现有见闻不能替代入场修为。', MIRROR_ID),
    OmenDefinition('stone_resonance', '旧石回声', 'wudi_plain', '无棣原',
        '旧石上的纹路在无风时仍有微弱回声，附近砂砾随之轻颤。尚不能解释来源，可以在当地核对。',
        '反复对照确认石纹与附近旧阵同起同落，可作为寻找遗址的地面标记。元婴后才可感知入口，尚无异界来历或另一端坐标。', RUINS_ID),
)
OMEN_IDS = frozenset(row.id for row in OMENS)


def validate_omen_definition(raw):
    if type(raw) is not dict or set(raw) != set(asdict(OMENS[0])):
        raise ValueError('诸天征兆定义字段无效')
    base = next((row for row in OMENS if row.id == raw['id']), None)
    if not base or any(raw[key] != getattr(base, key) for key in ('world', 'location_id', 'anomaly_id')):
        raise ValueError('诸天征兆必须关联实际本地异象')
    for key in ('name', 'location_name', 'glimpse', 'finding'):
        if not isinstance(raw[key], str) or not 0 < len(raw[key]) <= 1000:
            raise ValueError('诸天征兆说明无效')
    for key in ('revision', 'study_years', 'cooldown_years', 'lifetime_years'):
        if type(raw[key]) is not int or raw[key] != getattr(base, key):
            raise ValueError('诸天征兆初值或版本无效')


@dataclass(frozen=True, slots=True)
class RuinsDefinition:
    revision: int = 1
    world: str = 'human'
    location_id: str = 'wudi_plain'
    linked_world: str = 'demon'
    linked_location_id: str = 'red_marrow_city'
    observe_years: int = 2
    verify_years: int = 4
    read_years: int = 6
    take_years: int = 1
    replace_years: int = 8
    erase_years: int = 3
    contact_years: int = 4
    return_years: int = 2
    replace_stones: int = 500
    erase_stones: int = 300
    mana_fraction: float = .05
    guardian_power: float = 2200.0
    trace_read_years: int = 6
    trace_send_years: int = 4


def validate_ruins_definition(raw):
    base = asdict(RuinsDefinition())
    if type(raw) is not dict or set(raw) != set(base):
        raise ValueError('因果遗址定义字段无效')
    for key in ('revision', 'world', 'location_id', 'linked_world', 'linked_location_id'):
        if type(raw[key]) is not type(base[key]) or raw[key] != base[key]:
            raise ValueError('因果遗址来源、关联端或版本无效')
    for key in base.keys() - {'revision', 'world', 'location_id', 'linked_world', 'linked_location_id', 'mana_fraction', 'guardian_power'}:
        if type(raw[key]) is not int or not 1 <= raw[key] <= (10000 if key.endswith('_stones') else 100):
            raise ValueError('因果遗址耗时或成本无效')
    if type(raw['mana_fraction']) not in (int, float) or not 0 < raw['mana_fraction'] <= .05:
        raise ValueError('因果遗址法力成本无效')
    if type(raw['guardian_power']) not in (int, float) or not 1 <= raw['guardian_power'] <= 100000:
        raise ValueError('因果遗址守护强度无效')


@dataclass(frozen=True, slots=True)
class MirrorDefinition:
    revision: int = 1
    world: str = 'human'
    location_id: str = 'muling_desert'
    probe_years: int = 2
    decipher_years: int = 4
    isolate_years: int = 3
    assault_years: int = 1
    mana_fraction: float = .05
    collection_fraction: float = .25
    capacity_fraction: float = .25
    strength_cap: float = .15
    guardian_power: float = 2200.0


def validate_mirror_definition(raw):
    if type(raw) is not dict or set(raw) != set(asdict(MirrorDefinition())):
        raise ValueError('镜律场域定义字段无效')
    if type(raw['revision']) is not int or raw['revision'] != 1 or (raw['world'], raw['location_id']) != ('human', 'muling_desert'):
        raise ValueError('镜律场域来源或版本无效')
    for key in ('probe_years', 'decipher_years', 'isolate_years', 'assault_years'):
        if type(raw[key]) is not int or not 1 <= raw[key] <= 100:
            raise ValueError('镜律场域耗时无效')
    for key, ceiling in (('mana_fraction', .05), ('collection_fraction', .25), ('capacity_fraction', .25), ('strength_cap', .15)):
        if type(raw[key]) not in (int, float) or not 0 < raw[key] <= ceiling:
            raise ValueError('镜律场域收集或增幅超出预算')
    if type(raw['guardian_power']) not in (int, float) or not 1 <= raw['guardian_power'] <= 100000:
        raise ValueError('镜律场域守护强度无效')


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
    milestone: str = 'M3-R2'
    generation_available: bool = False
    sea_echo: SeaEchoDefinition = field(default_factory=SeaEchoDefinition)
    contact_sites: tuple[ContactSite, ...] = CONTACT_SITES
    mirror: MirrorDefinition = field(default_factory=MirrorDefinition)
    ruins: RuinsDefinition = field(default_factory=RuinsDefinition)
    omens: tuple[OmenDefinition, ...] = OMENS

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
    if 'mirror' in framework:
        validate_mirror_definition(framework['mirror'])
    if 'ruins' in framework:
        validate_ruins_definition(framework['ruins'])
    if 'omens' in framework:
        if type(framework['omens']) is not list or len(framework['omens']) != 2:
            raise ValueError('诸天征兆目录无效')
        for row in framework['omens']:
            validate_omen_definition(row)
        if {row['id'] for row in framework['omens']} != OMEN_IDS:
            raise ValueError('诸天征兆身份重复或缺失')
    if 'contact_sites' in framework:
        rows = framework['contact_sites']
        if type(rows) is not list or len(rows) != 4:
            raise ValueError('诸天联系须覆盖四个最高界面')
        for row in rows:
            validate_site(row)
        if {row['id'] for row in rows} != SITE_IDS or {row['world'] for row in rows} != set(members):
            raise ValueError('诸天联系须唯一覆盖四个最高界面')
