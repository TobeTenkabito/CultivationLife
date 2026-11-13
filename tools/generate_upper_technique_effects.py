"""Freeze effects on the 48 existing three-world upper manuals; no new books."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cultivation_life.technique_effect_generation import upper_effect
from cultivation_life.technique_effect_schema import describe


def build(document):
    rows = {row['id']: row for row in document['techniques']}
    worlds = {'asura': '修罗血战：承伤蓄势、危中反攻。', 'nether': '幽冥妖法：分期复苏、连击追猎。',
              'reincarnation': '轮回魂法：奇轮蓄护破法，偶轮回流追击。'}
    changed = 0
    for world, introduction in worlds.items():
        for grade in range(9, 13):
            for role in ('MAIN', 'COMBAT', 'BODY', 'SENSE'):
                row = rows[f'TECH_{world.upper()}_{grade}_{role}']
                if (row.get('combat_effect') or {}).get('version') == 3:
                    # The reviewed 4258 compiler now owns fixed-book metadata.
                    continue
                effect = upper_effect(world, role, grade)
                description = introduction + describe(effect)
                changed += row.get('combat_effect') != effect or row.get('description') != description
                row.update(combat_effect=effect, description=description)
    return changed


def render(original, document):
    """Preserve compact unrelated catalog rows and all surrounding formatting."""
    decoder = json.JSONDecoder()
    cursor = original.index('"techniques": [') + len('"techniques": [')
    replacements = []
    rows = {row['id']: row for row in document['techniques']}
    while True:
        while original[cursor].isspace() or original[cursor] == ',':
            cursor += 1
        if original[cursor] == ']':
            break
        row, end = decoder.raw_decode(original, cursor)
        if row != rows[row['id']]:
            formatted = json.dumps(rows[row['id']], ensure_ascii=False, indent=2)
            replacements.append((cursor, end, formatted.replace('\n', '\n    ')))
        cursor = end
    for start, end, value in reversed(replacements):
        original = original[:start] + value + original[end:]
    return original


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    path = ROOT / 'content/techniques.json'
    original = path.read_text(encoding='utf-8')
    document = json.loads(original)
    changed = build(document)
    if args.check:
        print(f'Upper manual effect drift: {changed} / 48')
        raise SystemExit(1 if changed else 0)
    path.write_text(render(original, document), encoding='utf-8')
    print(f'Updated {changed} / 48 upper manuals')
