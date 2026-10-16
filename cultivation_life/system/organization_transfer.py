"""Read-only personnel eligibility shared by the command and its candidate list."""
from ..npc_custody import is_free
from ..person_assignments import research_assignment
from ..spatial_people import accessible
from .intrigue.prison_state import is_imprisoned
from .war.occupancy import busy


def refusal(game, npc, source=None, destination=None):
    if not is_free(npc) or is_imprisoned(game, npc.id):
        return '此人被拘禁或已退出自由名册，不能调动宗籍'
    if research_assignment(game, npc.id):
        return '此人正在出征、返乡或执行其他任务，暂不能调动'
    if not accessible(game, npc):
        return '此人不在当前界面或空间，不能调动'
    for org in (source, destination):
        if org and (org.extinct or org.world != game.player.world):
            return '只能在当前界面的存续组织之间调动人事'
        if org and busy(game, org):
            return '双方宗门须完全闲置，战役和撤军结束前不能调动人事'
    return ''
