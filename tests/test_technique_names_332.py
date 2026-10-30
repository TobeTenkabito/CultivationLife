"""Complete titles and real saved ownership survive this display-only revision."""
import copy
from pathlib import Path

from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.engine import GameEngine
from cultivation_life.rules import combat_power, max_hp, max_mp, public_catalog_entry
from fixtures.technique_names_release import BOOK, GHOST, prepare_technique_names, inspect_technique_names
from tools.generate_common_techniques import FAMILIES, LINES, ROLES
from tools.common_technique_names import technique_name

ROOT = Path(__file__).resolve().parents[1]


def test_complete_titles_are_unique_without_old_stage_prefixes():
    names = [t.name for t in TECHNIQUE_CATALOG.values()]
    assert len(names) == len(set(names))
    for path, (_, titles, stems) in LINES.items():
        for grade, (prefix, stem) in enumerate(zip(titles, stems), 1):
            for family, (_, old_names) in FAMILIES.items():
                for i, role in enumerate(ROLES):
                    book = TECHNIQUE_CATALOG[f'TECH_OPEN_{stem}_{family.upper()}_{role.upper()}']
                    assert book.name == technique_name(path, grade, family, role)
                    assert len(book.name) == 5 and len(set(book.name)) == 5
                    assert book.name != prefix + old_names[i]
                    assert not book.name.endswith('抱朴归真经')


def test_real_load_and_upgrade_preserve_identity_stats_custom_text_and_file(tmp_path):
    engine = GameEngine(ROOT, tmp_path/'saves')
    identity = engine.create_game('新书旧藏', 'supreme_metal', 'dao', 332)['id']
    before_game = prepare_technique_names(engine, identity)
    before_stats = tuple(f(before_game.player) for f in (combat_power, max_hp, max_mp))
    path = engine.store._path(identity)
    before = path.read_bytes()
    shown = engine.present(engine._load(identity))
    game = inspect_technique_names(engine, identity)
    assert tuple(f(game.player) for f in (combat_power, max_hp, max_mp)) == before_stats
    assert path.read_bytes() == before
    assert any(t['id'] == GHOST and t['name'] == '晦烛含魄篇' for t in shown['player']['known_techniques'])
    old = dict(kind='technique', content_id=BOOK, name='松窗抱朴归真经', price=987, sold=False)
    snapshot = copy.deepcopy(old)
    offer = public_catalog_entry(old)
    assert (offer['name'],offer['price'],offer['sold']) == ('抱朴养真经',987,False)
    assert old == snapshot
    engine.upgrade_technique(identity, BOOK)
    after = inspect_technique_names(engine, identity, upgraded=True)
    assert after.rng_state == before_game.rng_state and after.player.age == before_game.player.age
