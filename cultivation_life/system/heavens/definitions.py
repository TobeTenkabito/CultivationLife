"""Finite M1 action scope and framework definition validation."""
from dataclasses import dataclass, field, asdict

VIEWS = frozenset({'known', 'opportunities', 'tasks', 'history'})
ACTIONS = frozenset({'configure', 'watch', 'dismiss', 'observe', 'check_history',
                     'exchange', 'attune', 'maintain', 'resume', 'cancel'})


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
    milestone: str = 'M1'
    generation_available: bool = False
    sea_echo: SeaEchoDefinition = field(default_factory=SeaEchoDefinition)


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
