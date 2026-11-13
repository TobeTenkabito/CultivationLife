"""Audit the reviewed title manifest and export the complete old/new index."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.common_technique_names import technique_name
from tools.generate_common_techniques import FAMILIES, LINES, ROLES

OUT = ROOT / 'docs' / 'technique-name-rewrite-3888'
PATH_LABELS = dict(dao='道修', demonic='魔修', monster='妖修', ghost='鬼修')
ROLE_LABELS = dict(main='修炼', support='辅助', combat='杀伐')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def audit():
    manifest = json.loads((OUT / 'names.json').read_text(encoding='utf-8'))
    content = json.loads((ROOT / 'content/techniques.json').read_text(encoding='utf-8'))
    books = content['techniques']
    catalog = {row['id']: row for row in books}
    reviewed = manifest['techniques']
    names = [row['name'] for row in reviewed]
    expected_ids = {
        f'TECH_OPEN_{stem}_{family.upper()}_{role.upper()}'
        for _, _, stems in LINES.values() for stem in stems
        for family in FAMILIES for role in ROLES
    }
    assert len(reviewed) == len(names) == len(set(names)) == 3888
    assert {row['id'] for row in reviewed} == expected_ids
    assert len(books) == len(catalog) == len({row['name'] for row in books}) == 4258
    assert {row['id'] for row in books if row['id'].startswith('TECH_OPEN_')} == expected_ids
    for row in reviewed:
        assert row['name'] != row['old_name'], row['id']
        assert catalog[row['id']]['name'] == row['name'], row['id']
        assert row['name'] == technique_name(row['path'], row['grade'], row['family'], row['role'])
    # Reject the former paired-prefix and suffix-only substitutions. Shared
    # genre vocabulary alone is not a duplicate or a claim of plagiarism.
    for start in range(0, len(reviewed), 3):
        assert len({row['name'][:2] for row in reviewed[start:start+3]}) == 3, reviewed[start:start+3]
    assert all(a['name'][:2] != b['name'][:2] for a, b in zip(reviewed, reviewed[1:])), '相邻书名重复双字前缀'
    stems = [name.rstrip('经诀录篇法书典藏图术') for name in names]
    assert len(stems) == len(set(stems)), '仅换体裁尾字的近似书名'
    design = json.loads((ROOT/'docs/technique-design-4258/techniques.json').read_text(encoding='utf-8'))
    revision = design['source']['title_revision']
    assert revision['manifest_hash_format'] == 'canonical_json_utf8_sorted_compact'
    assert revision['manifest_sha256'] == digest(manifest), '设计目录的重命名审阅记录不一致'
    return manifest, content, dict(
        status='passed', rewritten=3888, fixed_catalog=4258, unchanged_fixed=370,
        duplicate_names=0, unchanged_open_names=0, suffix_only_collisions=0,
        paired_prefix_groups=0, adjacent_duplicate_prefixes=0,
        lengths=dict(sorted(Counter(map(len, names)).items())),
        most_common_two_character_prefix=Counter(n[:2] for n in names).most_common(1),
    )


def render(manifest, report):
    lines = [
        '# 3888部功法完整重命名对照', '',
        '2026-11-14。按固定目录顺序列出全部3888条；[JSON清单](names.json) · [校验记录](validation.json) · [维护说明](README.md)。', '',
        '同一ID对应同一部功法，仅书名改变。前370部保留；专属机制、描述、灵根条件、品阶、等级与数值不变。', '',
    ]
    group = None
    for index, row in enumerate(manifest['techniques'], 1):
        key = row['path'], row['grade']
        if key != group:
            group = key
            lines += [f"## {PATH_LABELS[row['path']]} · {row['grade']}阶", '',
                      '| 序号 | ID | 类别 | 原名 | 新名 |', '| --- | --- | --- | --- | --- |']
        lines.append(f"| {index} | `{row['id']}` | {ROLE_LABELS[row['role']]} | {row['old_name']} | {row['name']} |")
        if index % 81 == 0:
            lines.append('')
    return {'names.md': '\n'.join(lines) + '\n',
            'validation.json': json.dumps(report, ensure_ascii=False, indent=2) + '\n'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--verify-original-values', action='store_true',
                        help='Additionally compare all non-name fields with the pre-rename snapshot')
    args = parser.parse_args()
    manifest, content, report = audit()
    if args.verify_original_values:
        fixed = [row for row in content['techniques'] if not row['id'].startswith('TECH_OPEN_')]
        assert digest(fixed) == manifest['baseline_fixed_370_sha256']
        for row in content['techniques']:
            row.pop('name')
        assert digest(content) == manifest['baseline_non_name_sha256']
        market = json.loads((ROOT / 'content/market.json').read_text(encoding='utf-8'))
        assert digest(market) == manifest['baseline_market_sha256']
        print('Original-value check passed: only 3888 names changed; fixed books and market unchanged.')
    for name, text in render(manifest, report).items():
        file = OUT / name
        if args.write:
            file.write_text(text, encoding='utf-8')
        elif not file.is_file() or file.read_text(encoding='utf-8') != text:
            raise SystemExit(f'Title artifact differs: {file}')
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    main()
