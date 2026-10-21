"""Disposable UI fixture; forging and binding use the original commands."""
import random
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.rules import add_item
from cultivation_life.system.crafting_system import crafting_material_definitions, make_crafting_material_instance


def prepare_visual_release(engine, identity):
    definitions=crafting_material_definitions()
    for index in range(2):
        game=engine._load(identity);game.pending_event=None
        instances=[make_crafting_material_instance(definitions[mid],random.Random(800+index*10+i),source='隔离验收',origin_world='human')
                   for i,mid in enumerate(['human_cold_iron','human_cloud_silk','human_cloud_silk','human_sun_fire'])]
        game.player.crafting_materials.extend(instances);engine.store.save(game)
        engine.forge_crafted_artifact(identity,dict(mold_id='umbrella',primary_id=instances[0]['id'],secondary_a_id=instances[1]['id'],
            secondary_b_id=instances[2]['id'],quench_id=instances[3]['id'],name='听雨伞',allocations={'combat_power':20,'max_hp':10,'max_mp':10,'breakthrough_bonus':5}))
    game=engine._load(identity)
    game.pending_event=None
    game.settings.update(silent_events=True,combat_popup=False)
    add_item(game.player,'healing_pill',2)
    add_item(game.player,'guixu_canghai_equipment_01')
    add_item(game.player,'spirit_stone',100000000000000)
    materials=[r for r in WORLD_SYSTEMS['natal_artifact']['materials'] if r['item_id'].startswith('natal_human_') and r['minimum_realm']==3]
    for row in materials:add_item(game.player,row['item_id'],2)
    engine.store.save(game)
    engine.crafted_artifact_action(identity,game.player.crafted_artifacts[0]['id'],'natal')
    game=engine._load(identity)
    game.natal_artifact.update(level=30,slots=[None]*3,experience=0)
    engine._sync_natal_artifact_bonuses(game)
    game.player.hp=1
    engine.store.save(game)
    return materials[0]['item_id']
