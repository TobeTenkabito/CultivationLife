"""Discover every repository test; retain per-module, source-bound receipts."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.release_evidence import inputs_digest, file_digest, require
from scripts.westward_release_scope import BROWSERS
from cultivation_life.version import BASE_GAME_VERSION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--asura', action='store_true', help='Full regression plus Asura governance acceptance')
    parser.add_argument('--resume', type=Path)
    parser.add_argument('--checks-only', action='store_true')
    parser.add_argument('--retry-failed', action='store_true',
                        help='Recheck completed failed modules without duplicating running modules')
    args = parser.parse_args()
    browsers = BROWSERS + (['browser_asura_governorship', 'browser_asura_politics', 'browser_asura_military', 'browser_asura_development', 'browser_asura_protocols'] if args.asura else [])
    require(1 <= args.workers <= 8, 'Use 1–8 workers')
    require(not (args.checks_only and args.retry_failed), 'Choose one helper mode')
    require(not args.retry_failed or args.resume, 'Failed-module retry requires an existing run')
    folder = args.resume or ROOT / 'build' / ('full-westward-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    digest = inputs_digest(ROOT)
    (ROOT / 'build/full-westward-latest.txt').write_text(str(folder), encoding='utf8')
    manifest_path = folder / 'manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf8'))
        require(manifest['inputs_sha256'] == digest, 'Source changed: start a new full run')
    else:
        collected = subprocess.run([sys.executable, '-m', 'pytest', 'tests', '--collect-only', '-q'],
                                   cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf8',
                                   env=os.environ | {'PYTHONIOENCODING': 'utf-8'})
        (folder / 'collection.log').write_text(collected.stdout, encoding='utf8')
        require(collected.returncode == 0, 'Full collection failed')
        nodes = [s.strip() for s in collected.stdout.splitlines() if s.startswith('tests/') and '::' in s]
        require(nodes and len(nodes) == len(set(nodes)), 'Empty or duplicate collection')
        modules = sorted({n.split('::')[0] for n in nodes})
        manifest = dict(inputs_sha256=digest, nodes=nodes, modules=modules)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf8')
    print(f"Full discovery: {len(manifest['nodes'])} cases, {len(manifest['modules'])} modules; {folder}", flush=True)

    def run(name, argv, test=None):
        receipt = folder / (name + '.json')
        log = folder / (name + '.log')
        source = file_digest(ROOT / test) if test else None
        if receipt.exists():
            old = json.loads(receipt.read_text(encoding='utf8'))
            if old['status'] == 'passed' and old['test_sha256'] == source and old['log_sha256'] == file_digest(log):
                return old
            import shutil
            archive = folder / 'previous-attempts' / (name + '-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
            archive.mkdir(parents=True, exist_ok=True)
            for path in (receipt, log, folder / (name + '.xml')):
                if path.exists():
                    shutil.copy2(path, archive / path.name)
        with log.open('w', encoding='utf8') as out:
            code = subprocess.call([sys.executable, '-X', 'utf8', *argv], cwd=ROOT, stdout=out,
                                   stderr=subprocess.STDOUT, env=os.environ | {'CULTIVATION_BROWSER_LOW_MEMORY': '0'})
        row = dict(name=name, test=test, test_sha256=source, inputs_sha256=digest,
                   log=log.relative_to(ROOT).as_posix(), log_sha256=file_digest(log),
                   status='passed' if code == 0 else 'failed', exit_code=code)
        require(inputs_digest(ROOT) == digest, 'Source changed during full regression')
        receipt.write_text(json.dumps(row, indent=2), encoding='utf8')
        print(name + ': ' + row['status'], flush=True)
        return row

    if args.checks_only:
        checks = [(n, [f'tools/{n}.py'], f'tools/{n}.py') for n in
                  ('check_world_transition_contract', 'check_module_dependencies', 'check_documentation')]
        checks += [(n, [f'tests/{n}.py'], f'tests/{n}.py') for n in browsers]
        checks += [('save-transfer', ['-m', 'pytest', 'tests/test_save_transfer.py', '-q'], 'tests/test_save_transfer.py')]
        for name, argv, source in checks:
            row = run(name, argv, source)
            require(row['status'] == 'passed', name + ' failed')
        return

    modules = manifest['modules']
    if args.retry_failed:
        modules = [module for module in modules
                   if (folder / (Path(module).stem + '.json')).exists()
                   and json.loads((folder / (Path(module).stem + '.json')).read_text(encoding='utf8'))['status'] == 'failed']
        print(f'Rechecking {len(modules)} completed failed modules', flush=True)
    runs = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = []
        for module in modules:
            name = Path(module).stem
            argv = ['-m', 'pytest', module, '-q', '--tb=short', '--assert=plain', '--junitxml=' + str(folder / (name + '.xml'))]
            futures.append(executor.submit(run, name, argv, module))
        for f in as_completed(futures):
            runs.append(f.result())
            progress = 'retry-progress.json' if args.retry_failed else 'progress.json'
            (folder / progress).write_text(json.dumps(dict(done=len(runs), total=len(futures),
                failed=[r['name'] for r in runs if r['status'] != 'passed']), indent=2), encoding='utf8')
    require(all(r['status'] == 'passed' for r in runs), 'Full regression failed; see individual receipts')
    if args.retry_failed:
        return
    combined = ET.Element('testsuites')
    count = 0
    for module in manifest['modules']:
        xml = folder / (Path(module).stem + '.xml')
        suites = list(ET.parse(xml).getroot().iter('testsuite'))
        count += sum(int(s.get('tests', 0)) for s in suites)
        combined.extend(suites)
    require(count == len(manifest['nodes']), 'Executed count differs from full discovery')
    tag = BASE_GAME_VERSION.replace('.', '')
    combined_path = ROOT / f'build/scoped-{tag}.xml'
    ET.ElementTree(combined).write(combined_path, encoding='utf-8', xml_declaration=True)
    ET.parse(combined_path)  # Validate the declaration even with non-ASCII hostnames.
    checks = [(n, [f'tools/{n}.py'], f'tools/{n}.py') for n in
              ('check_world_transition_contract', 'check_module_dependencies', 'check_documentation')]
    checks += [(n, [f'tests/{n}.py'], f'tests/{n}.py') for n in browsers]
    checks += [('save-transfer', ['-m', 'pytest', 'tests/test_save_transfer.py', '-q'], 'tests/test_save_transfer.py')]
    for name, argv, source in checks:
        row = run(name, argv, source)
        runs.append(row)
        require(row['status'] == 'passed', name + ' failed')
    import shutil
    shutil.copyfile(folder / 'save-transfer.log', ROOT / f'build/save-transfer-{tag}.log')
    doc = dict(version=BASE_GAME_VERSION, inputs_sha256=digest, profile='asura' if args.asura else 'westward',
               regression_scope='full-repository', collection=manifest_path.relative_to(ROOT).as_posix(),
               collection_sha256=file_digest(manifest_path), scope='Full repository pytest discovery; original institution, Asura governance, DLC palettes, Westward, managed caravans and shared event/navigation browser suites; final EXE and signed Android 12 native verification.' if args.asura else 'Full repository pytest discovery; Westward, managed caravans and shared event/navigation browser suites; final EXE and signed Android 12 native verification.',
               tests=[manifest['modules']], runs=runs)
    (ROOT / f'build/scoped-{tag}.json').write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf8')


if __name__ == '__main__':
    main()
