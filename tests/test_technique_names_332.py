"""Complete titles and real saved ownership survive this display-only revision."""
import copy
import json
from pathlib import Path

import pytest

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
                    assert 3 <= len(book.name) <= 9
                    assert book.name != prefix + old_names[i]
                    assert not book.name.endswith('抱朴归真经')


@pytest.mark.parametrize('old_names', [
    ('松窗抱朴归真经', '长夜抱朴归真经'),
    ('抱朴养真经', '晦烛含魄篇'),
])
def test_real_load_and_upgrade_preserve_identity_stats_custom_text_and_file(tmp_path, old_names):
    engine = GameEngine(ROOT, tmp_path/'saves')
    identity = engine.create_game('新书旧藏', 'supreme_metal', 'dao', 332)['id']
    before_game = prepare_technique_names(engine, identity, old_names)
    before_stats = tuple(f(before_game.player) for f in (combat_power, max_hp, max_mp))
    path = engine.store._path(identity)
    before = path.read_bytes()
    shown = engine.present(engine._load(identity))
    game = inspect_technique_names(engine, identity)
    assert tuple(f(game.player) for f in (combat_power, max_hp, max_mp)) == before_stats
    assert path.read_bytes() == before
    assert any(t['id'] == GHOST and t['name'] == '旧梦拾遗篇' for t in shown['player']['known_techniques'])
    old = dict(kind='technique', content_id=BOOK, name='松窗抱朴归真经', price=987, sold=False)
    snapshot = copy.deepcopy(old)
    offer = public_catalog_entry(old)
    assert (offer['name'],offer['price'],offer['sold']) == ('坐忘小乘',987,False)
    assert old == snapshot
    engine.upgrade_technique(identity, BOOK)
    after = inspect_technique_names(engine, identity, upgraded=True)
    assert after.rng_state == before_game.rng_state and after.player.age == before_game.player.age


def test_reviewed_manifest_covers_every_book_and_exported_index():
    from tools.export_common_technique_titles import OUT, audit, render
    manifest, _, report = audit()
    for name, text in render(manifest, report).items():
        assert (OUT / name).read_text(encoding='utf-8') == text
    design = json.loads((ROOT/'docs/technique-design-4258/techniques.json').read_text(encoding='utf-8'))
    by_id = {row['id']: row for row in design['techniques']}
    for row in manifest['techniques']:
        assert by_id[row['id']]['name'] == by_id[row['id']]['original_definition']['name'] == row['name']


def test_existing_npc_uses_new_names_without_rerolling_books_or_levels():
    from types import SimpleNamespace
    from cultivation_life.system.npc_techniques import public
    from cultivation_life.system.duel_techniques import npc_books
    game = SimpleNamespace(doctrine_state={}, authored_techniques={})
    npc = dict(id='seen-reader', realm_index=8, path='dao', spirit_root='supreme_metal',
               main_technique_id=BOOK, main_technique_level=5,
               technique_levels={BOOK: 5}, duel_technique_ids=[BOOK])
    before = copy.deepcopy(npc)
    assert public(game, npc) == [dict(id=BOOK, name='坐忘小乘', level=5)]
    combat_books = npc_books(game, npc)
    assert [(book.id, book.name, book.level) for book in combat_books] == [(BOOK, '坐忘小乘', 5)]
    assert npc == before
