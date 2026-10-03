"""Check repository Markdown links, topic coverage and release identity claims.

Historical changelog entries and distribution copies retain their own versions.
This check is deliberately offline; it does not validate prose or remote URLs.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r'\[[^\]\n]*\]\((<[^>]+>|[^\s)]+)(?:\s+"[^"]*")?\)')


def declared_value(path: Path, name: str):
    """Read a literal declaration without loading the game or content registry."""
    for node in ast.parse(path.read_text(encoding='utf-8-sig')).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError(f'{path}: missing {name}')


def markdown_paths(root: Path) -> list[Path]:
    result = subprocess.run(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
        cwd=root, check=True, capture_output=True,
    )
    return sorted({root / path for path in result.stdout.decode('utf-8').split('\0')
                   if path.lower().endswith('.md') and (root/path).is_file()})


def check_links(path: Path, text: str) -> list[str]:
    problems = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), 1):
        if re.match(r'^\s*(```|~~~)', line):
            in_fence = not in_fence
        if in_fence:
            continue
        for match in LINK.finditer(line):
            target = match.group(1).strip('<>')
            parsed = urlsplit(target)
            if parsed.scheme or target.startswith(('#', '//')):
                continue
            location = unquote(parsed.path)
            if location and not (path.parent/location).exists():
                problems.append(f'{path}:{number}: missing link target {location}')
    return problems


def check(root: Path = ROOT) -> dict:
    paths = markdown_paths(root)
    texts = {path: path.read_text(encoding='utf-8-sig') for path in paths}
    problems = [error for path, text in texts.items() for error in check_links(path, text)]
    version = declared_value(root/'cultivation_life/version.py', 'BASE_GAME_VERSION')
    schema = declared_value(root/'cultivation_life/save_schema.py', 'SAVE_SCHEMA_VERSION')
    minimum = declared_value(root/'cultivation_life/save_schema.py', 'MIN_SAVE_SCHEMA_VERSION')
    readme = texts[root/'README.md']
    if f'**当前本体版本：v{version}**' not in readme:
        problems.append('README.md: current base version differs from version.py')
    if f'存档结构 **{schema}**' not in readme or f'**{minimum} → {schema}**' not in readme:
        problems.append('README.md: current save schema/support range differs from save_schema.py')
    index = texts[root/'docs/README.md']
    for path in paths:
        if path.parent == root/'docs' and path.name != 'README.md' and f']({path.name})' not in index:
            problems.append(f'docs/README.md: missing topic {path.name}')
    manifests = sorted((root/'dlc').glob('*/manifest.json'))
    for path in manifests:
        manifest = json.loads(path.read_text(encoding='utf-8-sig'))
        prefix = f'dlc/{path.parent.name}/'
        rows = [line for line in readme.splitlines() if ']('+prefix in line]
        if len(rows) != 1 or f"| {manifest['version']} |" not in rows[0]:
            problems.append(f'README.md: DLC version/list mismatch for {manifest["id"]}')
        package_readme = path.parent/'README.md'
        if package_readme not in texts or manifest['version'] not in texts[package_readme]:
            problems.append(f'{package_readme}: missing current package version')
        rows = [line for line in texts[root/'dlc/README.md'].splitlines()
                if f']({path.parent.name}/README.md)' in line]
        if len(rows) != 1 or f"| {manifest['version']} |" not in rows[0]:
            problems.append(f'dlc/README.md: package table mismatch for {manifest["id"]}')
    gradle = (root/'android/app/build.gradle').read_text(encoding='utf-8')
    code = re.search(r'\bversionCode\s+(\d+)', gradle).group(1)
    if f'{version}-android.{code}' not in texts[root/'android/README.md']:
        problems.append('android/README.md: Android identity differs from Gradle')
    return dict(markdown_files=len(paths), base_version=version, save_schema=schema,
                minimum_save_schema=minimum, official_dlcs=len(manifests), problems=problems)


if __name__ == '__main__':
    report = check()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(bool(report['problems']))
