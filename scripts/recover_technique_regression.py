"""Resume interrupted release shards without counting incomplete cases as passes.

Only final-source cases recorded PASSED in both JUnit and the original verbose
log are retained. Changed test modules must explicitly opt into a complete
module rerun; none of their old cases are retained. Original evidence is kept,
and merged results must contain each originally collected node once.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.release_evidence import file_digest, inputs_digest, require
from cultivation_life.version import BASE_GAME_VERSION


def node_id(case, modules):
    classname = case.get('classname', '')
    for module in modules:
        prefix = module[:-3].replace('/', '.')
        if classname == prefix or classname.startswith(prefix + '.'):
            classes = classname[len(prefix):].strip('.').replace('.', '::')
            return module + '::' + (classes + '::' if classes else '') + case.get('name', '')
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--shards', nargs='+', type=int, required=True)
    parser.add_argument('--workers', type=int, default=1, choices=(1, 2))
    parser.add_argument('--retest-changed-modules', action='store_true')
    args = parser.parse_args()
    folder = ROOT / f'build/techniques-release-{BASE_GAME_VERSION.replace(".", "")}'
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    require(inputs_digest(ROOT) == manifest['inputs_sha256'], 'Final source changed')

    def recover(index):
        name = f'shard-{index}'
        receipt = folder / f'{name}.json'
        original = json.loads(receipt.read_text(encoding='utf-8'))
        require(original['status'] in {'failed','passed'}, 'Only finished shards may be reconciled')
        hashes = {p: file_digest(ROOT / p) for p in original['source_hashes']}
        changed = {p for p, h in original['source_hashes'].items() if hashes[p] != h}
        require(original['status']=='failed' or (changed and args.retest_changed_modules),
                'A passed shard may only rerun explicitly changed test modules')
        require(not changed or args.retest_changed_modules, 'Test source changed; complete module rerun required')
        require(file_digest(folder / f'{name}.log') == original['log_sha256'], 'Original log changed')
        archive = folder / f'{name}-interrupted'
        require(not archive.exists(), 'Recovery evidence already exists; inspect before retrying')
        archive.mkdir()
        for suffix in ('json', 'log', 'xml'):
            shutil.copyfile(folder / f'{name}.{suffix}', archive / f'original.{suffix}')
        (archive / 'test-source-changes.json').write_text(json.dumps({
            p: dict(before=original['source_hashes'][p], after=hashes[p]) for p in sorted(changed)
        }, indent=2), encoding='utf-8')
        modules = manifest['shards'][index]
        nodes = [n for n in manifest['nodes'] if n.split('::')[0] in modules]
        log = (archive / 'original.log').read_text(encoding='utf-8')
        confirmed = {line.split(' PASSED [', 1)[0] for line in log.splitlines() if ' PASSED [' in line}
        passed = {}
        for case in ET.parse(archive / 'original.xml').getroot().iter('testcase'):
            identity = node_id(case, modules)
            if (identity in nodes and identity.split('::')[0] not in changed and identity in confirmed
                    and not any(case.find(k) is not None for k in ('failure', 'error', 'skipped'))):
                require(identity not in passed, 'Duplicate original test identity')
                passed[identity] = case
        remaining = [n for n in nodes if n not in passed]
        retry_xml, retry_log = archive / 'retry.xml', archive / 'retry.log'
        arguments = [*remaining, '-v', '--tb=short', f'--junitxml={retry_xml}']
        argument_file = archive / 'arguments.json'
        argument_file.write_text(json.dumps(arguments), encoding='utf-8')
        print(f'{name}: retaining {len(passed)} proven passes, running {len(remaining)} remaining cases', flush=True)
        with retry_log.open('w', encoding='utf-8') as stream:
            code = subprocess.call([sys.executable, '-X', 'utf8', '-c',
                'import json,sys,pytest; raise SystemExit(pytest.main(json.load(open(sys.argv[1], encoding="utf-8"))))',
                str(argument_file)], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        require(code == 0, f'{name} retry failed; original and retry evidence retained')
        require(inputs_digest(ROOT) == manifest['inputs_sha256'], 'Final source changed during recovery')
        require(all(file_digest(ROOT / p) == h for p, h in hashes.items()), 'Test source changed during recovery')
        retried = {}
        for case in ET.parse(retry_xml).getroot().iter('testcase'):
            identity = node_id(case, modules)
            require(identity in remaining and identity not in retried, 'Unexpected or duplicate retry identity')
            require(not any(case.find(k) is not None for k in ('failure', 'error', 'skipped')), 'Retry contains non-passing cases')
            retried[identity] = case
        require(set(retried) == set(remaining), 'Retry coverage incomplete')
        all_cases = passed | retried
        require(len(all_cases) == len(nodes), 'Merged discovery coverage differs')
        root = ET.Element('testsuites')
        suite = ET.SubElement(root, 'testsuite', name=name, tests=str(len(nodes)), errors='0', failures='0', skipped='0')
        for identity in nodes:
            suite.append(all_cases[identity])
        ET.ElementTree(root).write(folder / f'{name}.xml', encoding='utf-8', xml_declaration=True)
        final_log = folder / f'{name}.log'
        final_log.write_text(log + '\nFINAL-SOURCE RECOVERY: original failures are rerun below\n' + retry_log.read_text(encoding='utf-8'), encoding='utf-8')
        evidence = {p.relative_to(ROOT).as_posix(): file_digest(p) for p in archive.iterdir() if p.is_file()}
        original.update(status='passed', source_hashes=hashes, log_sha256=file_digest(final_log), xml_sha256=file_digest(folder / f'{name}.xml'),
            recovery=dict(retained_passes=len(passed), rerun_cases=len(retried), changed_modules=sorted(changed),
                          inputs_sha256=manifest['inputs_sha256'], evidence_sha256=evidence))
        receipt.write_text(json.dumps(original, indent=2), encoding='utf-8')
        print(f'{name}: all {len(nodes)} distinct cases passed', flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(recover, args.shards))


if __name__ == '__main__':
    main()
