"""Explicit personal capabilities inside isolated spaces; geography stays local."""
PERSONAL_COMMANDS = frozenset({
    'contact_action', 'manage_dao_companion', 'manage_dao_friend',
    'manage_party', 'leave_relationship', 'request_from_master', 'gift_disciple',
    'respond_disciple_request', 'relationship_violence', 'begin_relationship_capture',
    'manage_concubine', 'manage_concubine_status', 'captive_action',
    'puppet_action', 'refine_foreign_souls', 'secluded_refine_foreign_souls',
    'preview_puppet', 'craft_mechanical_puppet', 'train_owned', 'ghost_soul_action', 'ghost_attachment_action',
    'ghost_constraint_action', 'prepare_ghost_reincarnation', 'reincarnate_ghost',
    'preview_crafting', 'save_crafting_blueprint', 'forge_crafted_artifact', 'crafted_artifact_action',
    'refine_pill', 'reclaim_spirit_field', 'plant_spirit_crop', 'harvest_spirit_crop',
    'use_harvested_plant', 'irrigate_spirit_crop', 'manage_transformation',
    'absorb_transformation_material', 'batch_absorb_transformation_material',
    'natal_artifact_action', 'sage_refine_manual', 'sage_outer_king',
})
LOCAL_SOCIETY_COMMANDS = frozenset({
    'buddhist_action', 'sage_doctrine_action', 'sage_choose_sage', 'sage_toggle_recruitment', 'sage_debate',
})
PERSONAL_PANELS = frozenset({
    'heavens',
    'map', 'inventory', 'talisman', 'settings', 'secret-art', 'formation', 'combat-plan',
    'bloodline', 'relationship', 'world-npc', 'transformation', 'ghost-soul', 'ghost-attachment',
    'captive', 'puppet-workshop', 'crafting', 'spirit-field', 'natal-artifact',
    'sage-inner-outer', 'buddhist-wish', 'extension',
})


def scope_key(game):
    return (game.spatial_state.get('current') or game.player.world) if game.player.world in {'lost', 'rift'} else game.player.world


def site_key(game):
    scene = game.spatial_state.get('instances', {}).get(game.spatial_state.get('current'))
    return scene['location_id'] if scene and game.player.world in {'lost', 'rift'} else game.player.location_id


def panels(game):
    return sorted(PERSONAL_PANELS | ({'sage', 'buddhist', 'faction', 'family'} if game.player.world == 'lost' else set()))


def local_names(game, maps, world, location):
    scene = game.spatial_state.get('instances', {}).get(world)
    if scene:
        return scene['name'], next((r['name'] for r in scene['locations'] if r['id'] == location), scene['name'])
    from ..content_registry import WORLD_SYSTEMS
    return WORLD_SYSTEMS['world_names'].get(world, world), maps.location(world, location)['name']
