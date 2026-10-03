from __future__ import annotations
from ...models import GameState
from ...content_registry import MONSTER_BLOODLINE_SETTINGS
from ...content_registry import REALMS
from ...content_registry import WORLD_SYSTEMS
from ...system.npc_social import migrate_fixed_couple
from ...rules import opportunity_required
from ...rules import realm
from .dependencies import FoundationsPreparationDependencies


def prepare_foundations(deps: FoundationsPreparationDependencies, game: GameState) -> bool:
    from ...system.institutions import migrate_institutions
    from ...system.asura import ensure as ensure_asura
    institutions_changed = ensure_asura(game) | migrate_institutions(game)
    from ...system.asura_court import ensure as ensure_asura_court
    institutions_changed |= ensure_asura_court(game)
    from ...system.faction_geography import ensure_faction_sites
    renamed = ensure_faction_sites(game) or institutions_changed
    from ...system.cultivation_policy import ordinary_upper, bloodline_upper, opportunity_unbounded
    p = game.player
    if p.path == "monster" and not p.monster_species_id:
        p.monster_species_id = str(MONSTER_BLOODLINE_SETTINGS.get('default_species_id') or 'serpent')
        renamed = True
    if ordinary_upper(p) and not opportunity_unbounded(p) and not p.sealed_cultivation and not p.cultivation_suppression:
        required = opportunity_required(p)
        old_progress = (p.opportunity, p.awaiting_minor_breakthrough, p.awaiting_major_breakthrough, p.next_tribulation_age, p.awaiting_ascension)
        p.awaiting_ascension = False
        p.opportunity = min(p.opportunity, required)
        ready = p.opportunity >= required and not game.active_trial
        p.awaiting_minor_breakthrough = ready and p.layer < realm(p).layers and not bloodline_upper(p)
        p.awaiting_major_breakthrough = ready and (p.layer >= realm(p).layers or bloodline_upper(p)) and p.realm_index < len(REALMS) - 1
        if p.next_tribulation_age is None:
            p.next_tribulation_age = p.age + int(WORLD_SYSTEMS['breakthrough']['periodic_thunder']['interval_years'])
        renamed |= old_progress != (p.opportunity, p.awaiting_minor_breakthrough, p.awaiting_major_breakthrough, p.next_tribulation_age, p.awaiting_ascension)
    merchant_changed = deps._ensure_merchant(game)
    social_changed = migrate_fixed_couple(game)
    return bool(renamed or merchant_changed or social_changed)
