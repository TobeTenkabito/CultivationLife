"""Full discovered regression and actual browsers for technique/secret release."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cultivation_life.version import BASE_GAME_VERSION
from scripts.release_evidence import file_digest,inputs_digest,require
from scripts.verify_scoped_release import balanced_test_shards

BROWSERS=['browser_seeded_dungeons','browser_dungeon_loot','browser_authored_techniques','browser_clone_support','browser_wind_frost_techniques','browser_domain_replay','browser_technique_release','browser_duel_techniques','browser_combat_mechanisms',
    'browser_combat_replay','browser_combat_groups','browser_technique_secrets','browser_technique_secret_growth',
    'browser_secret_art_training','browser_events_212','browser_debug_systems','browser_handbook_revision']

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--shard',type=int,help='Retry one manifest shard, then stop before aggregate gates')
    parser.add_argument('--checks-only',action='store_true',help='Run gates and real browsers without producing full-regression approval')
    args=parser.parse_args()
    require(1<=args.workers<=4,'Use 1–4 workers')
    require(args.shard is None or args.resume,'A single-shard retry requires --resume')
    require(not args.checks_only or (args.resume and args.shard is None),'Checks require --resume and cannot select a shard')
    tag=BASE_GAME_VERSION.replace('.','');folder=ROOT/f'build/techniques-release-{tag}'
    folder.mkdir(parents=True,exist_ok=True);digest=inputs_digest(ROOT)
    manifest_path=folder/'manifest.json'
    if args.resume:
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        require(manifest['inputs_sha256']==digest,'Release source changed; start a fresh full run')
    else:
        collection=subprocess.run([sys.executable,'-X','utf8','-m','pytest','tests','--collect-only','-q'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        (folder/'collection.log').write_text(collection.stdout+collection.stderr,encoding='utf-8')
        require(collection.returncode==0,'Collection failed')
        nodes=[s for s in collection.stdout.splitlines() if s.startswith('tests/') and '::' in s]
        modules=sorted({n.split('::')[0] for n in nodes});require(nodes and len(nodes)==len(set(nodes)),'Bad collection')
        history=list((ROOT/'build/secret-audit-20261114/complete').glob('shard-*.xml'))
        shards=balanced_test_shards(modules,args.workers,history)
        manifest=dict(inputs_sha256=digest,nodes=nodes,modules=modules,shards=shards)
        manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(f"Full discovery: {len(manifest['nodes'])} cases, {len(manifest['modules'])} modules",flush=True)
    def run(name,argv,sources):
        receipt=folder/f'{name}.json';log=folder/f'{name}.log'
        hashes={n:file_digest(ROOT/n) for n in sources}
        if args.resume and receipt.exists():
            previous=json.loads(receipt.read_text(encoding='utf-8'))
            if previous['status']=='passed' and previous['source_hashes']==hashes and previous['log_sha256']==file_digest(log):return previous
        import shutil,time
        existing=[p for p in (receipt,log,folder/f'{name}.xml') if p.exists()]
        if existing:
            archive=folder/'attempts'/f'{name}-{time.time_ns()}'
            archive.mkdir(parents=True)
            for path in existing:shutil.copy2(path,archive/path.name)
        with log.open('w',encoding='utf-8') as stream:
            code=subprocess.call([sys.executable,'-X','utf8',*argv],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,env=os.environ|{'PYTHONIOENCODING':'utf-8'})
        require(inputs_digest(ROOT)==digest,'Release inputs changed during acceptance')
        row=dict(name=name,status='passed' if code==0 else 'failed',log=log.relative_to(ROOT).as_posix(),log_sha256=file_digest(log),source_hashes=hashes)
        receipt.write_text(json.dumps(row,indent=2),encoding='utf-8');print(name+': '+row['status'],flush=True)
        return row
    def shard(i):
        modules=manifest['shards'][i]
        return run(f'shard-{i}',['-m','pytest',*modules,'-v','--tb=short',f'--junitxml={folder/f"shard-{i}.xml"}'],modules)
    if args.shard is not None:
        require(0<=args.shard<len(manifest['shards']),'Unknown manifest shard')
        require(shard(args.shard)['status']=='passed','Shard retry failed')
        return
    runs=[]
    if not args.checks_only:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:runs=list(pool.map(shard,range(len(manifest['shards']))))
        require(all(r['status']=='passed' for r in runs),'Full regression failed; retain logs and repair before --resume')
        combined=ET.Element('testsuites')
        for i in range(len(manifest['shards'])):combined.extend(ET.parse(folder/f'shard-{i}.xml').getroot().iter('testsuite'))
        require(sum(int(s.get('tests',0)) for s in combined)==len(manifest['nodes']),'Full coverage differs from discovery')
        ET.ElementTree(combined).write(ROOT/f'build/scoped-{tag}.xml',encoding='utf-8',xml_declaration=True)
    checks=[(n,[f'tools/{n}.py'],[f'tools/{n}.py']) for n in ('check_world_transition_contract','check_module_dependencies','check_documentation')]
    checks += [(n,[f'tests/{n}.py'],[f'tests/{n}.py']) for n in BROWSERS]
    checks += [('save-transfer',['-m','pytest','tests/test_save_transfer.py','-q'],['tests/test_save_transfer.py'])]
    for name,argv,sources in checks:
        row=run(name,argv,sources);runs.append(row);require(row['status']=='passed',f'{name} failed')
    import shutil
    shutil.copyfile(folder/'save-transfer.log',ROOT/f'build/save-transfer-{tag}.log')
    if args.checks_only:return
    document=dict(version=BASE_GAME_VERSION,inputs_sha256=digest,profile='techniques',regression_scope='full-repository',
        collection=manifest_path.relative_to(ROOT).as_posix(),collection_sha256=file_digest(manifest_path),
        scope='Full repository regression; seeded dungeons, frozen rewards, team/faction choices, mailbox, reputation, universal manuals, cultivation categories, prose, seven-book combat, secrets and real browser commands; final Windows and signed Android 12 dungeon and technique acceptance.',
        tests=manifest['shards'],runs=runs)
    (ROOT/f'build/scoped-{tag}.json').write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
