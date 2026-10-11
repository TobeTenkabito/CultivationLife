"""Debug capability availability; gameplay remains the authority on eligibility."""
from ..system.asura import enabled as asura_available
from ..system.buddhist.rules import buddhist_config
from ..system.guixu_system import guixu_content_available
from ..system.monster_bloodline_system import bloodline_content_available
from ..system.sage_system import sage_content_available
from ..system.tianji_system import tianji_content_available
from ..system.monster_civilizations.core import config as civilizations_config


CHECKS = {
    'official.monster-civilizations': lambda: bool(civilizations_config()),
    'official.asura-manifestation': asura_available,
    'official.buddhist-dharma': lambda: bool(buddhist_config().get('enabled')),
    'official.guixu-tide': guixu_content_available,
    'official.monster-bloodlines': bloodline_content_available,
    'official.sage-way': sage_content_available,
    'official.tianji-artifacts': tianji_content_available,
}


def available(dlc):
    return not dlc or CHECKS[dlc]()
