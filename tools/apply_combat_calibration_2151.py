"""Apply the reviewed, simulation-derived base table and linked story ratings.

One-shot authoring utility, never run during loading, birth or year settlement.
Requires the untouched v2.15.0 content snapshot and recorded pre-change starts.
"""
import copy
import json
import math
import os
import re
from pathlib import Path
import sys
import tempfile
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = ROOT/'build/common-goods-baseline-2150/content'
NEW = {
    'mortal': {'value': 20}, 'qi': {'base': 140, 'layer_step': 12},
    'foundation': {'early': 600, 'middle': 1000, 'late': 1150},
    'core': {'early': 2500, 'middle': 6100, 'late': 8800},
    'nascent': {'early': 35200, 'middle': 47700, 'late': 64500},
    'spirit': {'early': 194000, 'middle': 255000, 'late': 317000},
    'void': {'early': 1140000, 'middle': 1500000, 'late': 1860000},
    'integration': {'early': 8400000, 'middle': 11100000, 'late': 13900000},
    'mahayana': {'early': 46600000, 'middle': 60600000, 'late': 74100000},
    'true_immortal': {'value': 251000000}, 'golden_immortal': {'value': 990000000},
    'taiyi': {'value': 5580000000}, 'daluo': {'value': 34900000000},
}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def write_event(path, value, template):
    """Replace parsed scalar tokens while retaining the authored JSON layout."""
    decoder = json.JSONDecoder()
    edits = []
    def walk(index, expected):
        index = re.compile(r'\s*').match(template,index).end()
        if template[index] == '{':
            index += 1
            while True:
                index = re.compile(r'\s*').match(template,index).end()
                if template[index] == '}':
                    return index+1
                key, index = decoder.raw_decode(template,index)
                index = re.compile(r'\s*').match(template,index).end()
                assert template[index] == ':'
                index = walk(index+1,expected[key])
                index = re.compile(r'\s*').match(template,index).end()
                if template[index] == ',':
                    index += 1
        elif template[index] == '[':
            index += 1
            position = 0
            while True:
                index = re.compile(r'\s*').match(template,index).end()
                if template[index] == ']':
                    assert position == len(expected)
                    return index+1
                index = walk(index,expected[position])
                position += 1
                index = re.compile(r'\s*').match(template,index).end()
                if template[index] == ',':
                    index += 1
        else:
            current, end = decoder.raw_decode(template,index)
            if current != expected:
                edits.append((index,end,json.dumps(expected,ensure_ascii=False)))
            return end
    walk(0,value)
    text = template
    for start,end,replacement in reversed(edits):
        text = text[:start]+replacement+text[end:]
    assert json.loads(text) == value
    path.write_text(text,encoding='utf-8')


def rounded(value):
    unit = 10**max(0, math.floor(math.log10(value))-2)
    return int(round(value/unit)*unit)


def main():
    original = read(BASE/'world.json')['systems']['combat_expectations']
    world = read(ROOT/'content/world.json')
    assert set(NEW) == set(original), (set(NEW), set(original))
    world['systems']['combat_expectations'] = copy.deepcopy(NEW)
    world['systems']['player_combat_recommendations'] = copy.deepcopy(NEW)
    # Integer levels of actual equipped books, not a fabricated permanent bonus.
    temporary = tempfile.TemporaryDirectory(prefix='author-combat-')
    shutil.copytree(ROOT/'content', Path(temporary.name)/'content')
    os.environ['CULTIVATION_APP_ROOT'] = temporary.name
    from cultivation_life.models import Player
    from cultivation_life.content_registry import TECHNIQUE_CATALOG
    from cultivation_life.rules import combat_power, assign_technique
    starts = read(ROOT/'build/combat-calibration-2151/quick-before-base.json')['rows']
    levels = {}
    start_rows = []
    realms = read(BASE/'world.json')['realms']
    realm_ids = {i:r['id'] for i,r in enumerate(realms)}
    for row in starts:
        if row['preset'] == 'lost_world':
            continue
        old_values = original[realm_ids[row['rank']]]
        new_values = NEW[realm_ids[row['rank']]]
        key = 'value' if 'value' in old_values else 'early'
        target = row['power'] * new_values[key]/old_values[key]
        initial = Player.from_dict(row['player'])
        initial.quick_start_base_combat_power = 0
        extras = []
        native = initial.path if initial.path in {'demonic','monster','ghost'} else 'dao'
        for book in sorted(TECHNIQUE_CATALOG.values(),key=lambda t:t.combat_bonus,reverse=True):
            if not book.id.startswith('TECH_OPEN_') or book.path != native or book.grade > initial.realm_index:
                continue
            if any(t.id == book.id for t in initial.combat_techniques):
                continue
            probe = copy.deepcopy(initial)
            try:
                assign_technique(probe,copy.deepcopy(book),'combat')
            except ValueError:
                continue
            extras.append(book)
            if len(extras)==3:
                break
        found = False
        for extra_count in range(len(extras)+1):
            for level in range(1, 10):
                player = copy.deepcopy(initial)
                for book in extras[:extra_count]:
                    assign_technique(player,copy.deepcopy(book),'combat')
                combat_ids = {t.id for t in player.combat_techniques}
                for t in [player.technique, player.support_technique, *player.combat_techniques, *player.known_techniques]:
                    if t and t.id in combat_ids:
                        t.level = level
                from cultivation_life.rules import max_hp, max_mp
                player.hp, player.mp = max_hp(player), max_mp(player)
                if combat_power(player) >= target:
                    found = True
                    break
            if found:
                break
        chosen = level
        assert combat_power(player) >= target, row['preset']
        levels[row['preset']] = (chosen,[t.id for t in extras[:extra_count]])
        start_rows.append(dict(preset=row['preset'],old_power=row['power'],target=target,
                               level=chosen,extra_arts=levels[row['preset']][1],actual_power=combat_power(player)))
    original_presets = {p['id']:p for p in read(BASE/'world.json')['systems']['quick_start_presets']}
    for preset in world['systems']['quick_start_presets']:
        if preset['id'] in levels:
            level, extras = levels[preset['id']]
            preset['combat_technique_level'] = level
            preset['combat_techniques'] = original_presets[preset['id']]['combat_techniques']
            preset['supplementary_combat_techniques'] = extras
    write(ROOT/'content/world.json', world)
    # Keep each story's relation to its nearest intended realm stage. The
    # normal adapter consumes this threat once; explicit boss power is separate.
    scenarios = {r['event_id'] for r in read(BASE/'story_combat_scenarios.json')['scenarios']}
    rows = []
    for path in sorted(BASE.glob('*events*.json')):
        old_doc = read(path)
        old_events = old_doc if isinstance(old_doc,list) else old_doc.get('events', [])
        target = ROOT/'content'/path.name
        doc = read(target)
        events = doc if isinstance(doc,list) else doc.get('events', [])
        by_id = {e['id']:e for e in events}
        changed = False
        for old_event in old_events:
            if old_event['id'] not in scenarios:
                continue
            event = by_id[old_event['id']]
            tags = old_event.get('tags', [])
            intended = next((t[6:] for t in tags if t.startswith('realm:')), None)
            if intended is None:
                intended = ('foundation' if 'BLOOD_RIVER' in event['id'] else
                    'core' if 'CORPSE_MOON' in event['id'] else
                    'nascent' if 'RIFT_BEAST' in event['id'] else
                    'void' if 'BLACK_SUN' in event['id'] else
                    'integration' if 'FALLEN_STAR' in event['id'] else 'mahayana')
            old_stages, new_stages = original[intended], NEW[intended]
            replacements = {}
            for old_choice, choice in zip(old_event['choices'], event['choices']):
                assert old_choice['id'] == choice['id']
                for old_effect, effect in zip(old_choice.get('effects', []), choice.get('effects', [])):
                    for old_check, check in zip(old_effect.get('checks', []), effect.get('checks', [])):
                        if old_check.get('stat') != 'combat_power':
                            continue
                        old_power = old_check['value']
                        stage = min(old_stages, key=lambda k:abs(old_stages[k]-old_power))
                        new_power = max(old_power, rounded(old_power*new_stages[stage]/old_stages[stage]))
                        check['value'] = new_power
                        replacements[old_power] = new_power
                        if new_power != old_power:
                            rows.append(dict(event=event['id'],choice=choice['id'],realm=intended,
                                stage=stage,old=old_power,new=new_power))
                            changed = True
                choice['text'] = old_choice['text']
                for old_power, new_power in replacements.items():
                    choice['text'] = choice['text'].replace(f'{old_power:,}', f'{new_power:,}')
            event['body'] = old_event['body']
            for old_power, new_power in replacements.items():
                event['body'] = event['body'].replace(f'{old_power:,}', f'{new_power:,}')
            if event['id'] == 'EVT_MA_LIANG_005':
                # The seventy-percent MP preparation figure uses the same stage.
                event['body'] = event['body'].replace('115,000,000', '135,000,000')
        if changed:
            write_event(target,doc,path.read_text(encoding='utf-8'))
    output = ROOT/'build/combat-calibration-2151/authored.json'
    write(output, dict(benchmarks=NEW,quick_starts=start_rows,stories=rows))
    print(json.dumps(dict(quick_starts=start_rows,story_choices=len(rows)),ensure_ascii=False))


if __name__ == '__main__':
    main()
