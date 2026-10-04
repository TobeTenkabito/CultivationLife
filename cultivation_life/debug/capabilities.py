"""Explicit debug-only capabilities for ordinary game operations.

No dynamic method lookup, HTTP forwarding, or runtime generation. Keep this
allowlist reviewed alongside server routes; tests reject unclassified routes.
Optional fields are omitted from payloads, preserving ordinary API defaults.
"""
from dataclasses import dataclass
from typing import Callable

from .registry import Argument, Command
from ..system.crafted_artifact_rules import STAT_NAMES
from ..system.merchant_definitions import METRICS as FORMATION_METRICS


def S(name, *, required=True, choices=()):
    return Argument(name, choices, required=required)


def I(name, minimum=0, maximum=10**9, *, required=False):
    return Argument(name, type='integer', minimum=minimum, maximum=maximum, required=required)


def N(name, minimum=0, maximum=10**15, *, required=False):
    return Argument(name, type='number', minimum=minimum, maximum=maximum, required=required)


def B(name, *, required=False):
    return Argument(name, type='boolean', required=required)


def O(name, properties, *, required=False):
    return Argument(name, type='object', required=required,
                    shape={'type': 'object', 'properties': properties, 'additionalProperties': False})


def A(name, items, maximum=999, *, required=False):
    return Argument(name, type='array', required=required,
                    shape={'type': 'array', 'items': items, 'maxItems': maximum})


STRING = {'type': 'string', 'maxLength': 2048}
INTEGER = {'type': 'integer', 'minimum': 0, 'maximum': 10**9}
NUMBER = {'type': 'number', 'minimum': 0, 'maximum': 10**15}
MATERIAL = {'type': 'object', 'properties': {'item_id': STRING, 'quantity': {'type': 'integer', 'minimum': 1, 'maximum': 10**9}},
            'required': ['item_id', 'quantity'], 'additionalProperties': False}
EXCHANGE_MATERIAL = {**MATERIAL, 'properties': {'id': STRING, 'quantity': MATERIAL['properties']['quantity']}, 'required': ['id', 'quantity']}
CRAFTING_ARGS = (
    S('mold_id'), S('primary_id'), S('secondary_a_id'), S('secondary_b_id'), S('quench_id'),
    O('allocations', {key: INTEGER for key in STAT_NAMES}, required=True),
    S('name', required=False), S('blueprint_name', required=False),
)
FORMATION_ARGS = (A('slots', {'type': ['string', 'null']}, 9, required=True),
                  S('name', required=False), S('loadout_id', required=False), B('activate'))
METRICS = {key: {'type': 'number', 'minimum': 0, 'maximum': 100} for key in FORMATION_METRICS}
MERCHANT_ARGS = (
    S('alliance_id', required=False), S('task_id', required=False), S('destination', required=False),
    S('kind', required=False), I('stars', 1, 5), I('quantity', 1, 999), S('source_world', required=False),
    S('material_category', required=False), S('definition_id', required=False), S('target_id', required=False),
    I('principal', 0, 10**15), I('material_tier', 0, 12), S('mold_id', required=False),
    O('metrics', METRICS), O('metric_maxima', METRICS), S('preview_token', required=False),
)
FAMILY_ARGS = (S('action'), S('npc_id', required=False), S('technique_id', required=False),
    S('item_id', required=False), B('enabled'), S('partner_id', required=False), S('sect_id', required=False),
    S('target_id', required=False), S('status', required=False), I('amount', 0, 10**15))
COMBAT_ARGS = (S('stance', required=False, choices=('press', 'guard', 'protect', 'off')),
    N('investment', 0, 1000000), S('burst', required=False, choices=('auto', 'early', 'never')),
    N('mp_reserve', 0, 1), B('transformations'), B('support_guard'))
TIANJI_ARGS = (S('target_artifact_id'), *CRAFTING_ARGS[:5],
               S('forge_kind', required=False, choices=('replica', 'true_body')))
LINEAGE_RULE = {
    'type': 'object',
    'properties': {**{key: STRING for key in ('phase', 'schedule', 'condition', 'target', 'effect')},
                   'value': {'type': 'number'}},
    'required': ['phase', 'schedule', 'condition', 'target', 'effect', 'value'],
    'additionalProperties': False,
}


@dataclass(frozen=True)
class Capability:
    name: str
    operation: str
    arguments: tuple[Argument, ...]
    invoke: Callable
    preview: bool = False
    dlc: str = ''
    shortcut: bool = False


CAPABILITIES = (
    Capability('spatial action', 'spatial-action',
        (S('action', choices=('open','enter','descend','explore','move','join','talk')), S('target_id', required=False)),
        lambda e,g,p: e.spatial_action(g,p['action'],p)),
    Capability('talisman action', 'talisman-action',
        (S('action', choices=('learn','craft','toggle','discard')), S('method_id',required=False),
         S('material1',required=False), S('material2',required=False), S('element',required=False),
         S('npc_id',required=False), S('talisman_id',required=False)),
        lambda e,g,p: e.talisman_action(g,p['action'],p)),
    Capability('action advance', 'advance', (S('action', required=False), I('years', 0, 10)),
        lambda e, g, p: e.advance(g, p.get('action', 'cultivate'), p.get('years', 1))),
    Capability('event choose', 'choice', (S('choice_id'),),
        lambda e, g, p: e.choose(g, p.get('choice_id', ''))),
    Capability('npc contact', 'npc-contact', (S('npc_id'), S('action', choices=('party', 'companion', 'friend', 'master', 'disciple', 'concubine', 'slay', 'improve', 'worsen', 'capture'))),
        lambda e, g, p: e.contact_action(g, p.get('npc_id', ''), p.get('action', ''))),
    Capability('relationship violence', 'relationship-violence', (S('kind'), S('target_id'), B('capture')),
        lambda e, g, p: e.relationship_violence(g, **p)),
    Capability('doctrine action', 'doctrine-action', (S('action'), S('doctrine_id', required=False), S('manual_id', required=False), B('confirm_origin'), S('npc_id', required=False)),
        lambda e, g, p: e.doctrine_action(g, str(p.get('action', '')), p.get('doctrine_id'), p.get('manual_id'), p.get('confirm_origin', False), p.get('npc_id'))),
    Capability('aperture action', 'aperture-action', (S('action', choices=('select', 'refine')), S('manual_id', required=False)),
        lambda e, g, p: e.aperture_action(g, str(p.get('action', '')), p.get('manual_id'))),
    Capability('upper institution', 'upper-institution', (S('action'), S('target_id', required=False)),
        lambda e, g, p: e.upper_institution_action(g, str(p.get('action', '')), str(p.get('target_id', '')))),
    Capability('upper voisinage', 'upper-voisinage', (S('action', choices=('select', 'train')), S('voisinage_id', required=False)),
        lambda e, g, p: e.upper_voisinage_action(g, str(p.get('action', '')), p.get('voisinage_id'))),
    Capability('immortal action', 'immortal-action', (S('action'), S('doctrine_id', required=False), S('axis', required=False), S('supply_id', required=False)),
        lambda e, g, p: e.immortal_action(g, str(p.get('action', '')), p.get('doctrine_id'), p.get('axis'), p.get('supply_id'))),
    Capability('yaochi action', 'yaochi-action', (S('action'), S('target_id', required=False), I('amount', 0, 1000000000000000)),
        lambda e, g, p: e.yaochi_action(g, p.get('action', ''), p.get('target_id', ''), p.get('amount', 1))),
    Capability('item use', 'use-item', (S('item_id'),),
        lambda e, g, p: e.use_item(g, p.get('item_id', ''))),
    Capability('faction reward', 'faction-reward', (S('reward_id'),),
        lambda e, g, p: e.set_faction_reward(g, p.get('reward_id', ''))),
    Capability('faction succession', 'faction-succession', (),
        lambda e, g, p: e.arrange_faction_succession(g)),
    Capability('market buy', 'market-buy', (S('offer_id'),),
        lambda e, g, p: e.buy_market_offer(g, p.get('offer_id', ''))),
    Capability('market lock', 'market-lock', (S('offer_id'),),
        lambda e, g, p: e.toggle_market_offer_lock(g, p.get('offer_id', ''))),
    Capability('market sell plant', 'market-sell-plant', (S('item_id'),),
        lambda e, g, p: e.sell_spirit_plant(g, p.get('item_id', ''))),
    Capability('auction consign', 'auction-consign', (S('item_id'), I('start_price', 0, 1000000000000000)),
        lambda e, g, p: e.consign_auction_item(g, p.get('item_id', ''), int(p.get('start_price', 0) or 0))),
    Capability('auction bid', 'auction-bid', (S('lot_id'),),
        lambda e, g, p: e.place_auction_bid(g, p.get('lot_id', ''))),
    Capability('auction advance', 'auction-advance', (),
        lambda e, g, p: e.advance_auction_round(g)),
    Capability('auction negotiate', 'auction-negotiate', (S('npc_id'),),
        lambda e, g, p: e.negotiate_at_auction(g, p.get('npc_id', ''))),
    Capability('auction identity', 'auction-identity', (S('alias'),),
        lambda e, g, p: e.choose_auction_identity(g, p.get('alias', ''))),
    Capability('exchange action', 'exchange-action', (S('action'), S('alias', required=False), S('offer_id', required=False), A('materials', EXCHANGE_MATERIAL)),
        lambda e, g, p: e.exchange_action(g, p.get('action', ''), p)),
    Capability('merchant action', 'merchant-action', (S('action'), *MERCHANT_ARGS),
        lambda e, g, p: e.merchant_action(g, p.get('action', ''), p)),
    Capability('merchant preview', 'merchant-preview', MERCHANT_ARGS,
        lambda e, g, p: e.preview_merchant_commission(g, p), preview=True),
    Capability('auction private buy', 'auction-private-buy', (S('npc_id'), S('offer_id')),
        lambda e, g, p: e.buy_private_trade_item(g, p.get('npc_id', ''), p.get('offer_id', ''))),
    Capability('auction private sell', 'auction-private-sell', (S('npc_id'), S('item_id')),
        lambda e, g, p: e.sell_private_trade_item(g, p.get('npc_id', ''), p.get('item_id', ''))),
    Capability('auction private bargain', 'auction-private-bargain', (S('npc_id'), S('side'), S('asset_id')),
        lambda e, g, p: e.bargain_private_trade(g, p.get('npc_id', ''), p.get('side', ''), p.get('asset_id', ''))),
    Capability('transformation absorb', 'transformation-absorb', (S('item_id'), S('stat_id', required=False)),
        lambda e, g, p: e.absorb_transformation_material(g, p.get('item_id', ''), False, p.get('stat_id', ''))),
    Capability('transformation purify', 'transformation-purify', (S('item_id'), S('stat_id', required=False)),
        lambda e, g, p: e.absorb_transformation_material(g, p.get('item_id', ''), True, p.get('stat_id', ''))),
    Capability('transformation batch', 'transformation-batch', (S('item_id'), S('mode', required=False), S('stat_id', required=False)),
        lambda e, g, p: e.batch_absorb_transformation_material(g, p.get('item_id', ''), p.get('mode', 'direct'), p.get('stat_id', ''))),
    Capability('setting set', 'settings', (S('setting'), B('enabled')),
        lambda e, g, p: e.update_setting(g, p.get('setting', ''), bool(p.get('enabled', False)))),
    Capability('combat plan', 'combat-plan', COMBAT_ARGS,
        lambda e, g, p: e.update_combat_plan(g, p)),
    Capability('tutorial', 'tutorial', (S('action'), Argument('step', required=False,
        shape={'type': ['integer', 'string'], 'minimum': 0, 'maximum': 10**9}), S('target_id', required=False)),
        lambda e, g, p: e.tutorial_action(g, p.get('action', ''), p.get('step'), p.get('target_id'))),
    Capability('black market search', 'black-market-search', (S('pattern'),),
        lambda e, g, p: e.search_black_market(g, p.get('pattern', ''))),
    Capability('black market buy', 'black-market-buy', (S('result_id'), I('quantity', 0, 1000000000)),
        lambda e, g, p: e.buy_black_market_item(g, p.get('result_id', ''), p.get('quantity', 1))),
    Capability('black market sell', 'black-market-sell', (S('kind'), S('asset_id')),
        lambda e, g, p: e.sell_black_market_asset(g, p.get('kind', ''), p.get('asset_id', ''))),
    Capability('spirit field reclaim', 'spirit-field-reclaim', (),
        lambda e, g, p: e.reclaim_spirit_field(g)),
    Capability('spirit field plant', 'spirit-field-plant', (S('plant_id'), I('slot', 0, 1000)),
        lambda e, g, p: e.plant_spirit_crop(g, p.get('plant_id', ''), p.get('slot'))),
    Capability('spirit field irrigate', 'spirit-field-irrigate', (S('plot_id'), N('mp_amount'), S('booster_id', required=False)),
        lambda e, g, p: e.irrigate_spirit_crop(g, p.get('plot_id', ''), float(p.get('mp_amount', 0) or 0), p.get('booster_id', ''))),
    Capability('spirit field harvest', 'spirit-field-harvest', (S('plot_id'),),
        lambda e, g, p: e.harvest_spirit_crop(g, p.get('plot_id', ''))),
    Capability('alchemy refine', 'alchemy', (S('target_item_id'), A('materials', MATERIAL, required=True)),
        lambda e, g, p: e.refine_pill(g, p.get('target_item_id', ''), p.get('materials', []))),
    Capability('crafting preview', 'crafting-preview', CRAFTING_ARGS,
        lambda e, g, p: e.preview_crafting(g, p), preview=True),
    Capability('crafting forge', 'crafting-forge', CRAFTING_ARGS,
        lambda e, g, p: e.forge_crafted_artifact(g, p)),
    Capability('crafting blueprint', 'crafting-blueprint', CRAFTING_ARGS,
        lambda e, g, p: e.save_crafting_blueprint(g, p)),
    Capability('crafted artifact', 'crafted-artifact', (S('artifact_id'), S('action'), I('start_price', 0, 1000000000000000)),
        lambda e, g, p: e.crafted_artifact_action(g, p.get('artifact_id', ''), p.get('action', ''), int(p.get('start_price', 0) or 0))),
    Capability('formation preview', 'formation-preview', FORMATION_ARGS,
        lambda e, g, p: e.preview_formation(g, p), preview=True),
    Capability('formation save', 'formation-save', FORMATION_ARGS,
        lambda e, g, p: e.save_formation(g, p)),
    Capability('formation activate', 'formation-activate', (S('formation_id'),),
        lambda e, g, p: e.activate_formation(g, p.get('formation_id', ''))),
    Capability('formation deactivate', 'formation-deactivate', (),
        lambda e, g, p: e.deactivate_formation(g)),
    Capability('formation delete', 'formation-delete', (S('formation_id'),),
        lambda e, g, p: e.delete_formation(g, p.get('formation_id', ''))),
    Capability('formation ground deploy', 'formation-ground-deploy', (S('owner_kind', required=False),),
        lambda e, g, p: e.deploy_ground_formation(g, p.get('owner_kind', 'player'))),
    Capability('formation ground withdraw', 'formation-ground-withdraw', (S('ground_formation_id'),),
        lambda e, g, p: e.withdraw_ground_formation(g, p.get('ground_formation_id', ''))),
    Capability('formation ground repair', 'formation-ground-repair', (S('ground_formation_id'), S('supply_id', required=False), I('quantity', 0, 1000000000)),
        lambda e, g, p: e.repair_ground_formation(g, p.get('ground_formation_id', ''), p.get('supply_id', ''), int(p.get('quantity', 1) or 1))),
    Capability('spirit plant use', 'spirit-plant-use', (S('item_id'),),
        lambda e, g, p: e.use_harvested_plant(g, p.get('item_id', ''))),
    Capability('black market leave', 'black-market-leave', (),
        lambda e, g, p: e.leave_black_market(g)),
    Capability('teleport action', 'teleport-action', (S('action'), S('destination', required=False)),
        lambda e, g, p: e.teleport_action(g, p.get('action', ''), p.get('destination'))),
    Capability('map travel', 'map-travel', (S('destination'),),
        lambda e, g, p: e.travel_map(g, p.get('destination', ''))),
    Capability('technique equip', 'equip-technique', (S('technique_id'), S('slot', choices=('main', 'support', 'combat', 'body', 'divine_sense', 'transformation'))),
        lambda e, g, p: e.equip_known_technique(g, p.get('technique_id', ''), p.get('slot', ''))),
    Capability('technique upgrade', 'technique-upgrade', (S('technique_id'),),
        lambda e, g, p: e.upgrade_technique(g, p.get('technique_id', ''))),
    Capability('technique manual merge', 'technique-manual-merge', (S('technique_id'), I('level', 0, 1000000000)),
        lambda e, g, p: e.merge_technique_manuals(g, p.get('technique_id', ''), int(p.get('level', 1)))),
    Capability('transformation', 'transformation', (S('form_id'), S('action')),
        lambda e, g, p: e.manage_transformation(g, p.get('form_id', ''), p.get('action', ''))),
    Capability('body breakthrough', 'body-breakthrough', (),
        lambda e, g, p: e.body_breakthrough(g)),
    Capability('sense breakthrough', 'sense-breakthrough', (),
        lambda e, g, p: e.divine_sense_breakthrough(g)),
    Capability('secret art', 'secret-art', (S('art', choices=('conceal', 'suppress')), S('action', choices=('activate', 'cancel')), I('realm_index', 0, 12), I('layer', 1, 13)),
        lambda e, g, p: e.manage_secret_art(g, p.get('art', ''), p.get('action', ''), p.get('realm_index'), p.get('layer'))),
    Capability('ghost reincarnate', 'ghost-reincarnate', (),
        lambda e, g, p: e.reincarnate_ghost(g)),
    Capability('ghost reincarnation prompt', 'ghost-reincarnation-prompt', (),
        lambda e, g, p: e.prepare_ghost_reincarnation(g)),
    Capability('ghost wangsheng', 'ghost-wangsheng', (B('all'),),
        lambda e, g, p: e.spend_wangsheng(g, bool(p.get('all', False)))),
    Capability('ghost parade', 'ghost-parade', (S('soul_id'), S('action')),
        lambda e, g, p: e.ghost_parade_action(g, p.get('soul_id', ''), p.get('action', ''))),
    Capability('ghost soul', 'ghost-soul', (S('soul_id'), S('action'), S('slot', required=False)),
        lambda e, g, p: e.ghost_soul_action(g, p.get('soul_id', ''), p.get('action', ''), p.get('slot', ''))),
    Capability('ghost attachment', 'ghost-attachment', (S('action'), S('item_id', required=False)),
        lambda e, g, p: e.ghost_attachment_action(g, p.get('action', ''), p.get('item_id', ''))),
    Capability('ghost constraint', 'ghost-constraint', (S('action'),),
        lambda e, g, p: e.ghost_constraint_action(g, p.get('action', ''))),
    Capability('ghost leave host', 'ghost-leave-host', (),
        lambda e, g, p: e.leave_possessed_body(g)),
    Capability('post battle possession', 'post-battle-possession', (S('target_id', required=False),),
        lambda e, g, p: e.post_battle_possess(g, p.get('target_id', ''))),
    Capability('captive action', 'captive-action', (S('target_id'), S('action')),
        lambda e, g, p: e.captive_action(g, p.get('target_id', ''), p.get('action', ''))),
    Capability('concubine action', 'concubine-action', (S('target_id'), S('action')),
        lambda e, g, p: e.manage_concubine(g, p.get('target_id', ''), p.get('action', ''))),
    Capability('concubine status', 'concubine-status', (S('action'),),
        lambda e, g, p: e.manage_concubine_status(g, p.get('action', ''))),
    Capability('relationship capture', 'relationship-capture', (S('kind'), S('target_id', required=False)),
        lambda e, g, p: e.begin_relationship_capture(g, p.get('kind', ''), p.get('target_id', ''))),
    Capability('owned training', 'owned-training', (S('target_id'), S('kind'), S('axis', required=False), I('batches', 1, 100)),
        lambda e, g, p: e.train_owned(g, p.get('target_id', ''), p.get('kind', ''), p.get('axis', ''), p.get('batches', 1))),
    Capability('puppet action', 'puppet-action', (S('puppet_id'), S('action'), S('content_id', required=False)),
        lambda e, g, p: e.puppet_action(g, p.get('puppet_id', ''), p.get('action', ''), p.get('content_id', ''))),
    Capability('puppet preview', 'puppet-preview', (S('form'), S('core'), S('shell'), S('energy')),
        lambda e, g, p: e.preview_puppet(g, p.get('form', ''), p.get('core', ''), p.get('shell', ''), p.get('energy', '')), preview=True),
    Capability('craft puppet', 'craft-puppet', (S('form'), S('core'), S('shell'), S('energy')),
        lambda e, g, p: e.craft_mechanical_puppet(g, p.get('form', ''), p.get('core', ''), p.get('shell', ''), p.get('energy', ''))),
    Capability('refine souls', 'refine-souls', (),
        lambda e, g, p: e.refine_foreign_souls(g)),
    Capability('secluded refine souls', 'secluded-refine-souls', (),
        lambda e, g, p: e.secluded_refine_foreign_souls(g)),
    Capability('faction dispatch', 'faction-dispatch', (S('target'),),
        lambda e, g, p: e.dispatch_disciple(g, p.get('target', ''))),
    Capability('faction relationship', 'faction-relationship', (S('npc_id'), S('role')),
        lambda e, g, p: e.manage_faction_relationship(g, p.get('npc_id', ''), p.get('role', ''))),
    Capability('party', 'party', (S('npc_id'), S('action', choices=('invite', 'leave', 'interact', 'crossing_add', 'crossing_remove'))),
        lambda e, g, p: e.manage_party(g, p.get('npc_id', ''), p.get('action', ''))),
    Capability('dao companion', 'dao-companion', (S('action'), S('npc_id', required=False), S('kind', required=False), S('content_id', required=False)),
        lambda e, g, p: e.manage_dao_companion(g, p.get('action', ''), p.get('npc_id', ''), p.get('kind', ''), p.get('content_id', ''))),
    Capability('dao friend', 'dao-friend', (S('npc_id'), S('action')),
        lambda e, g, p: e.manage_dao_friend(g, p.get('npc_id', ''), p.get('action', ''))),
    Capability('relationship faction', 'relationship-faction', (S('npc_id'),),
        lambda e, g, p: e.invite_relationship_to_faction(g, p.get('npc_id', ''))),
    Capability('relationship exit', 'relationship-exit', (S('kind'), S('npc_id')),
        lambda e, g, p: e.leave_relationship(g, p.get('kind', ''), p.get('npc_id', ''))),
    Capability('leave faction', 'leave-faction', (),
        lambda e, g, p: e.leave_faction(g)),
    Capability('prison action', 'prison-action', (S('action'),),
        lambda e, g, p: e.prison_action(g, p.get('action', ''))),
    Capability('disciple request', 'disciple-request', (S('request_id'), B('accept')),
        lambda e, g, p: e.respond_disciple_request(g, p.get('request_id', ''), bool(p.get('accept', False)))),
    Capability('master request', 'master-request', (S('kind'),),
        lambda e, g, p: e.request_from_master(g, p.get('kind', ''))),
    Capability('disciple gift', 'disciple-gift', (S('disciple_id'), S('kind'), S('content_id', required=False)),
        lambda e, g, p: e.gift_disciple(g, p.get('disciple_id', ''), p.get('kind', ''), p.get('content_id', ''))),
    Capability('spirit crossing', 'spirit-crossing', (),
        lambda e, g, p: e.begin_spirit_crossing(g)),
    Capability('celestial ascension', 'celestial-ascension', (),
        lambda e, g, p: e.begin_celestial_ascension(g)),
    Capability('asura ascension', 'asura-ascension', (),
        lambda e, g, p: e.begin_asura_ascension(g)),
    Capability('heavenly election', 'heavenly-election', (S('method', required=False), S('pledge_id', required=False)),
        lambda e, g, p: e.resolve_heavenly_election(g, p.get('method', 'none'), p.get('pledge_id', ''))),
    Capability('heavenly court', 'heavenly-court', (S('action'), S('target_id', required=False), B('enact'), I('influence_spend', 0, 1000000000000000)),
        lambda e, g, p: e.heavenly_court_action(g, p.get('action', ''), p.get('target_id', ''), p.get('enact'), int(p.get('influence_spend', 0) or 0))),
    Capability('natal artifact', 'natal-artifact', (S('action'), S('item_id', required=False), I('slot_index', -1, 1000000000)),
        lambda e, g, p: e.natal_artifact_action(g, p.get('action', ''), p.get('item_id', ''), int(p.get('slot_index', -1)))),
    Capability('cross world', 'cross-world', (S('destination'),),
        lambda e, g, p: e.cross_world(g, p.get('destination', ''))),
    Capability('create faction', 'create-faction', (S('name'),),
        lambda e, g, p: e.create_faction(g, p.get('name', ''))),
    Capability('create family', 'create-family', (S('name'),),
        lambda e, g, p: e.create_family(g, p.get('name', ''))),
    Capability('family action', 'family-action', FAMILY_ARGS,
        lambda e, g, p: e.family_action(g, p.get('action', ''), p)),
    Capability('race diplomacy', 'race-diplomacy', (S('target_id'), S('status')),
        lambda e, g, p: e.propose_race_diplomacy(g, p.get('target_id', ''), p.get('status', ''))),
    Capability('faction diplomacy', 'faction-diplomacy', (S('target_id'), S('status')),
        lambda e, g, p: e.propose_sect_diplomacy(g, p.get('target_id', ''), p.get('status', ''))),
    Capability('vassal transfer', 'vassal-transfer', (S('kind'), S('target_id'), S('npc_id')),
        lambda e, g, p: e.transfer_vassal_personnel(g, p.get('kind', ''), p.get('target_id', ''), p.get('npc_id', ''))),
    Capability('war action', 'war-action', (S('war_id'), S('action'), S('ally_id', required=False)),
        lambda e, g, p: e.war_action(g, p.get('war_id', ''), p.get('action', ''), ally_id=p.get('ally_id', ''))),
    Capability('war peace', 'war-peace', (S('war_id'), S('term', required=False), S('target_id', required=False), S('target_power_id', required=False), S('third_party_id', required=False), S('third_status', required=False), B('concede')),
        lambda e, g, p: e.war_peace(g, p.get('war_id', ''), p.get('term', 'white_peace'), target_id=p.get('target_id', ''), target_power_id=p.get('target_power_id', ''), third_party_id=p.get('third_party_id', ''), third_status=p.get('third_status', 'neutral'), concede=bool(p.get('concede', False)))),
    Capability('issue bounty', 'issue-bounty', (S('npc_id'), S('authority')),
        lambda e, g, p: e.issue_bounty(g, p.get('npc_id', ''), p.get('authority', ''))),
    Capability('faction intercept', 'faction-intercept', (S('npc_id'),),
        lambda e, g, p: e.intercept_faction_npc(g, p.get('npc_id', ''))),
    Capability('intrigue personnel', 'intrigue-personnel', (S('kind'), S('action'), S('npc_id'), S('position_id', required=False), I('years', 0, 1000000000), S('reason', required=False)),
        lambda e, g, p: e.intrigue_personnel_action(g, p.get('kind', ''), p.get('action', ''), p.get('npc_id', ''), p.get('position_id', ''), int(p.get('years', 1) or 1), p.get('reason', ''))),
    Capability('intrigue guest', 'intrigue-guest', (S('kind'), S('action'), S('npc_id')),
        lambda e, g, p: e.intrigue_guest_action(g, p.get('kind', ''), p.get('action', ''), p.get('npc_id', ''))),
    Capability('intrigue resolution', 'intrigue-resolution', (S('kind'), S('resolution_type'), S('target_id', required=False), B('player_vote')),
        lambda e, g, p: e.intrigue_propose_resolution(g, p.get('kind', ''), p.get('resolution_type', ''), p.get('target_id', ''), bool(p.get('player_vote', True)))),
    Capability('intrigue recruitment', 'intrigue-recruitment', (S('action'), O('filters', {'spirit_root': STRING, 'realm_index': {'type': ['integer', 'string', 'null']}, 'path': STRING, 'combat': STRING, 'gender': STRING}), A('candidate_ids', STRING, 100), B('player_vote')),
        lambda e, g, p: e.intrigue_recruitment_action(g, p.get('action', ''), p.get('filters'), p.get('candidate_ids'), bool(p.get('player_vote', True)))),
    Capability('breakthrough attempt', 'breakthrough', (),
        lambda e, g, p: e.breakthrough(g)),
    Capability('world news set', 'debug-world-news', (B('enabled'),),
        lambda e, g, p: e.set_world_news_debug(g, bool(p.get('enabled', False)))),
    Capability('buddhist action', 'buddhist-action',
        (S('action', choices=('nirvana', 'blessing', 'temple', 'permission', 'start', 'continue', 'cancel')),
         S('blessing', required=False), S('authority', required=False), S('technique', required=False)),
        lambda e, g, p: e.buddhist_action(g, **p), dlc='official.buddhist-dharma'),
    Capability('guixu action', 'guixu-action',
        (S('action', choices=('enter', 'team_accept', 'team_decline', 'gift_treasure', 'threat_surrender',
            'threat_resist', 'move', 'search', 'return', 'rest', 'fight', 'flee', 'recruit', 'negotiate', 'trapped_cultivate')),
         S('dungeon_id', required=False), S('target_layer_id', required=False), S('actor_id', required=False),
         S('pool_entry_id', required=False), B('confirm_betrayal'), I('offer_stones', 0, 10**15)),
        lambda e, g, p: e.guixu_action(g, p['action'], p), dlc='official.guixu-tide'),
    Capability('asura action', 'asura',
        (S('action', choices=('purify', 'convert', 'train_body', 'open_vein', 'condense', 'fuse', 'rename',
            'train_route', 'choose_branch', 'train_branch', 'train_domain', 'nourish_domain',
            'lock_power', 'reroll_power', 'learn_power')),
         S('target_id', required=False), A('body_ids', STRING, 2), S('name', required=False)),
        lambda e, g, p: e.asura_action(g, p['action'], p.get('target_id', ''), p.get('body_ids'), p.get('name', '')),
        dlc='official.asura-manifestation'),
    Capability('tianji action', 'tianji-action', (S('action', choices=('activate', 'deactivate')), S('artifact_id')),
        lambda e, g, p: e.tianji_action(g, p['action'], p['artifact_id']), dlc='official.tianji-artifacts'),
    Capability('tianji preview', 'tianji-preview', TIANJI_ARGS,
        lambda e, g, p: e.preview_tianji_forge(g, p), preview=True, dlc='official.tianji-artifacts'),
    Capability('tianji forge', 'tianji-forge', TIANJI_ARGS,
        lambda e, g, p: e.forge_tianji_artifact(g, p), dlc='official.tianji-artifacts'),
    Capability('tianji reveal all', 'tianji-debug-reveal-all', (),
        lambda e, g, p: e.debug_reveal_all_tianji(g), dlc='official.tianji-artifacts', shortcut=True),
    Capability('sage doctrine', 'sage-doctrine',
        (S('action', choices=('join', 'leave', 'found')), S('doctrine_id', required=False),
         O('combo', {key: STRING for key in ('classic', 'philosophy', 'practice', 'script')}), S('name', required=False)),
        lambda e, g, p: e.sage_doctrine_action(g, p['action'], p), dlc='official.sage-way'),
    Capability('sage recruitment', 'sage-recruitment', (B('enabled'),),
        lambda e, g, p: e.sage_toggle_recruitment(g, p.get('enabled', True)), dlc='official.sage-way'),
    Capability('sage worship', 'sage-worship', (S('sage_id'),),
        lambda e, g, p: e.sage_choose_sage(g, p['sage_id']), dlc='official.sage-way'),
    Capability('sage debate', 'sage-debate', (S('doctrine_id'), S('member_id')),
        lambda e, g, p: e.sage_debate(g, p['doctrine_id'], p['member_id']), dlc='official.sage-way'),
    Capability('sage refine manual', 'sage-refine-manual', (S('item_id'),),
        lambda e, g, p: e.sage_refine_manual(g, p['item_id']), dlc='official.sage-way'),
    Capability('sage outer king', 'sage-outer-king',
        (S('action', choices=('advance', 'combat', 'spirit_stone', 'opportunity')),),
        lambda e, g, p: e.sage_outer_king(g, p['action']), dlc='official.sage-way'),
    Capability('monster evolve', 'monster-evolve', (S('evolution_id'),),
        lambda e, g, p: e.evolve_monster(g, p['evolution_id']), dlc='official.monster-bloodlines'),
    Capability('custom lineage prepare', 'custom-lineage-prepare', (S('evolution_id'),),
        lambda e, g, p: e.prepare_custom_lineage(g, p['evolution_id']), preview=True, dlc='official.monster-bloodlines'),
    Capability('custom lineage confirm', 'custom-lineage-confirm',
        (S('evolution_id'), S('name'), A('rules', LINEAGE_RULE, required=True)),
        lambda e, g, p: e.confirm_custom_lineage(g, p['evolution_id'], p['name'], p['rules']), dlc='official.monster-bloodlines'),
    Capability('merchant debug hq', 'merchant-debug-hq', (S('alliance_id'),),
        lambda e, g, p: e.debug_merchant_hq(g, p['alliance_id']), shortcut=True),
)
BY_OPERATION = {cap.operation: cap for cap in CAPABILITIES}


def register(registry):
    for capability in CAPABILITIES:
        if capability.operation in {'advance', 'choice'}:
            continue  # Established console names and signatures are retained.
        def invoke(ctx, *values, capability=capability):
            payload = {a.name: value for a, value in zip(capability.arguments, values) if value is not None}
            execute = ctx.services.preview if capability.preview else ctx.services.simulate
            return execute(ctx.session, capability.operation, payload)
        description = ('Compute in a disposable copy without committing preparation or RNG.' if capability.preview
                       else 'Execute ordinary game rules in the isolated session; costs, eligibility and event gates apply.')
        if capability.shortcut:
            description = 'Debug shortcut in the isolated session only; bypasses ordinary acquisition requirements.'
        if capability.dlc:
            description += f' Requires enabled DLC {capability.dlc}.'
        registry.register(Command(capability.name, 'preview' if capability.preview else 'simulation',
            description + ' Discover current IDs and options with game view.', invoke, capability.arguments))

EXCLUDED_OPERATIONS = {}
