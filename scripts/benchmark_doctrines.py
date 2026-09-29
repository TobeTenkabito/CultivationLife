"""Measure incremental doctrine costs; no timing assertions or yearly scans."""
import copy
import json
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_npc_combat import measure
from cultivation_life.content_registry import WORLD_SYSTEMS, CONTENT_DOCUMENTS
from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc
from cultivation_life.rules import expected_combat_power
from cultivation_life.system.combat.npc_lifecycle import initialize_native
from cultivation_life.system.combat.npc_battle import resolve_npc_engagement
from cultivation_life.system.doctrine.generation import generate
from cultivation_life.system.doctrine.provider import battle_sources, ensure


def main():
    powers = {r: expected_combat_power(r, 1) for r in range(9, 13)}
    result = {'catalog_once_ms': measure(lambda: None, lambda _: generate(7429, CONTENT_DOCUMENTS['doctrines.json'], powers))}
    with tempfile.TemporaryDirectory() as directory:
        engine = GameEngine(ROOT, Path(directory))
        made = engine.create_game('Benchmark', 'supreme_metal', 'dao', seed=7429, preset_id='true_immortal')
        game = engine.store.load(made['id'])
        result['1000_existing_catalog_checks_ms'] = measure(lambda: game, lambda g: [ensure(g) for _ in range(1000)])
        config = WORLD_SYSTEMS['transcendent_combat']
        def actors():
            rows = {f'n{i}': SectNpc(f'n{i}', 'NPC', '', 12, 1, 10000, None, world='celestial') for i in range(48)}
            for npc in rows.values():
                initialize_native(npc, config, now=game.player.age)
            return rows
        result['48_initial_doctrine_sources_ms'] = measure(actors, lambda rows: battle_sources(game, rows))
        original = actors()
        battle_sources(game, original)
        for elapsed in (100, 10000, 1000000):
            start = game.player.age
            game.player.age += elapsed
            result[f'48_lazy_sources_{elapsed}_years_ms'] = measure(lambda: copy.deepcopy(original), lambda rows: battle_sources(game, rows))
            game.player.age = start
        def fight(rows):
            sources = battle_sources(game, rows)
            units = list(rows.values())
            return resolve_npc_engagement([(n, powers[12]) for n in units[:24]], [(n, powers[12]) for n in units[24:]],
                                          config, random.Random(1), now=game.player.age, sources=sources)
        result['48_generated_voisinage_actors_fight_ms'] = measure(actors, fight)
        result['catalog_bytes'] = len(json.dumps(game.doctrine_state, ensure_ascii=False).encode('utf-8'))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
