"""Publish verified packages as GitHub assets, checking remote digests before cleanup."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.release_evidence import inputs_digest


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, encoding='utf-8').strip()


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def credential():
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token:
        return token
    result = subprocess.run(['git', 'credential', 'fill'], cwd=ROOT,
        input='protocol=https\nhost=github.com\n\n', capture_output=True, text=True,
        env=os.environ | {'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never'})
    values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if result.returncode or not values.get('password'):
        raise RuntimeError('No GitHub credential available from environment or Git credential manager')
    return values['password']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', required=True)
    parser.add_argument('--target', required=True, help='Already pushed commit SHA')
    parser.add_argument('--notes', type=Path, required=True)
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--cleanup', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[\w.]+)?', args.version):
        raise RuntimeError('Invalid version')
    if not re.fullmatch(r'[0-9a-f]{40}', args.target) or git('rev-parse', 'HEAD') != args.target:
        raise RuntimeError('Target must be the complete current commit SHA')
    if git('status', '--porcelain'):
        raise RuntimeError('Commit all release changes before publishing')
    remote = git('remote', 'get-url', 'origin')
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:)([^/]+/[^/]+?)(?:\.git)?', remote)
    if not match:
        raise RuntimeError('Origin is not a supported GitHub repository')
    repository = match.group(1)
    folder = (args.directory or ROOT / 'build/releases' / args.version).resolve()
    if not folder.is_relative_to((ROOT / 'build/releases').resolve()):
        raise RuntimeError('Release staging and cleanup must stay inside build/releases')
    manifests = sorted(folder.glob(f'release-{args.version}*.json'))
    if len(manifests) != 2:
        raise RuntimeError('Windows and Android acceptance manifests are required')
    windows, android = None, None
    for path in manifests:
        value = json.loads(path.read_text(encoding='utf-8'))
        if value['base_version'] != args.version or value['regression']['failures'] or value['regression']['errors']:
            raise RuntimeError('Invalid release acceptance manifest')
        if value['platform'] == 'Windows': windows = value
        if value['platform'] == 'Android 12': android = value
    if not windows or not android or not windows['with_and_without_dlc_verified'] or android['native']['status'] != 'passed':
        raise RuntimeError('Actual Windows and Android acceptance required')
    if windows['inputs_sha256']!=inputs_digest(ROOT) or android['inputs_sha256']!=windows['inputs_sha256']:
        raise RuntimeError('Acceptance manifests differ from the committed game inputs')
    assets = {}
    for suffix in ('.exe', '-Windows.zip', '-Android12.apk', '-Android12.zip'):
        path = folder / f'浮生问道-v{args.version}{suffix}'
        if not path.is_file():
            raise RuntimeError(f'Missing release artifact: {path.name}')
        assets[f'CultivationLife-v{args.version}{suffix}'] = path
    if digest(assets[f'CultivationLife-v{args.version}.exe']) != windows['exe_sha256']:
        raise RuntimeError('Windows artifact differs from verified executable')
    if digest(assets[f'CultivationLife-v{args.version}-Android12.apk']) != android['apk_sha256']:
        raise RuntimeError('Android artifact differs from verified APK')
    for suffix,entry,expected in [('-Windows.zip','launcher.exe',windows['exe_sha256']),
        ('-Android12.zip',f'浮生问道-v{args.version}-Android12.apk',android['apk_sha256'])]:
        with zipfile.ZipFile(assets[f'CultivationLife-v{args.version}{suffix}']) as archive:
            with archive.open(entry) as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=expected:
                    raise RuntimeError('Archived application differs from the accepted artifact')
    for path in sorted(folder.glob('*.zip')):
        if path in assets.values():continue
        with zipfile.ZipFile(path) as archive:
            entries=[n for n in archive.namelist() if re.fullmatch(r'dlc/[^/]+/manifest\.json',n)]
            if len(entries)!=1:raise RuntimeError('Cannot identify additional DLC bundle: '+path.name)
            dlc=json.loads(archive.read(entries[0]))
        name=f'DLC-{dlc["id"]}-v{dlc["version"]}.zip'
        if not re.fullmatch(r'[A-Za-z0-9._-]+',name) or name in assets:
            raise RuntimeError('Invalid or duplicate DLC asset identity')
        assets[name]=path
    assets.update({p.name: p for p in manifests})
    notes_path=args.notes.resolve()
    notes = notes_path.read_text(encoding='utf-8')
    def note_link(match):
        destination=(notes_path.parent/match.group(1)).resolve()
        if not destination.is_relative_to(ROOT):
            raise RuntimeError('Release note link leaves the repository')
        relative=urllib.parse.quote(destination.relative_to(ROOT).as_posix(),safe='/')
        return f'](https://github.com/{repository}/blob/{args.target}/{relative}{match.group(2) or ""})'
    notes=re.sub(r'\]\((?!https?://)([^)#]+)(#[^)]*)?\)',note_link,notes)
    regression=windows['regression']
    scope='全仓回归' if windows.get('regression_scope')=='full-repository' else '相关领域回归'
    browser_count=sum(r['name'].startswith('browser_') and r['status']=='passed' for r in windows['runs'])
    notes+=(f'\n## 发行验收摘要\n\n'
        f'- {scope}：{regression["passed"]}项通过，{regression["skipped"]}项跳过，0失败、0错误。\n'
        f'- 真实浏览器回归：{browser_count}项通过。\n'
        '- Windows：同一EXE有／无DLC验收通过。\n'
        f'- Android：{android["android_version"]}签名包验收通过；实际设备范围见所附发行清单。\n'
        f'- 源码提交：[{args.target[:12]}](https://github.com/{repository}/commit/{args.target})。\n')
    note_path = folder / 'RELEASE-NOTES.md'
    note_path.write_text(notes, encoding='utf-8')
    assets[note_path.name] = note_path
    hashes = {name: digest(path) for name, path in assets.items()}
    checksums = folder / 'SHA256SUMS.txt'
    checksums.write_text(''.join(f'{value}  {name}\n' for name, value in hashes.items()), encoding='utf-8')
    assets[checksums.name] = checksums
    hashes[checksums.name] = digest(checksums)
    if args.dry_run:
        print(json.dumps(dict(repository=repository, target=args.target, assets=hashes), indent=2))
        return
    token = credential()

    def request(method, path, data=None, upload=None, allow_missing=False):
        host = 'uploads.github.com' if upload else 'api.github.com'
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'CultivationLife-release'}
        proxy=urllib.parse.urlsplit(urllib.request.getproxies().get('https',''))
        if proxy.scheme=='http' and proxy.hostname:
            connection=http.client.HTTPSConnection(proxy.hostname,proxy.port or 80,timeout=180,blocksize=1024*1024)
            proxy_headers={}
            if proxy.username is not None:
                pair=urllib.parse.unquote(proxy.username)+':'+urllib.parse.unquote(proxy.password or '')
                proxy_headers['Proxy-Authorization']='Basic '+base64.b64encode(pair.encode()).decode()
            connection.set_tunnel(host,443,headers=proxy_headers)
        else:
            connection = http.client.HTTPSConnection(host, timeout=180,blocksize=1024*1024)
        body = json.dumps(data).encode('utf-8') if data is not None else None
        stream = None
        if upload:
            stream = upload.open('rb'); body = stream
            headers.update({'Content-Type': 'application/octet-stream', 'Content-Length': str(upload.stat().st_size)})
        elif body is not None:
            headers['Content-Type'] = 'application/json'
        try:
            if upload:
                connection.connect()
                connection.sock.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,4*1024*1024)
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse(); raw = response.read()
            if response.status == 404 and allow_missing: return None
            if not 200 <= response.status < 300:
                raise RuntimeError(f'GitHub {method} failed with HTTP {response.status}')
            return json.loads(raw) if raw else None
        finally:
            if stream: stream.close()
            connection.close()

    prefix = f'/repos/{repository}'
    request('GET', prefix + '/commits/' + args.target)
    tag = 'v' + args.version
    release = request('GET', prefix + '/releases/tags/' + tag, allow_missing=True)
    if release is None:
        drafts=[r for r in request('GET',prefix+'/releases?per_page=100') if r['tag_name']==tag]
        if len(drafts)>1:raise RuntimeError('Multiple releases use the requested tag')
        if drafts:release=drafts[0]
    if release is None:
        release = request('POST', prefix + '/releases', dict(tag_name=tag, target_commitish=args.target,
            name=f'浮生问道 {tag}', body=notes, draft=True, prerelease='-' in args.version))
    if release['target_commitish'] != args.target:
        raise RuntimeError('Existing release targets a different commit')
    existing = {asset['name']: asset for asset in request('GET', prefix + f'/releases/{release["id"]}/assets?per_page=100')}
    def upload_asset(item):
        name,path=item
        asset = existing.get(name)
        if asset and (asset.get('digest') != 'sha256:' + hashes[name] or asset['size'] != path.stat().st_size):
            if not release['draft']:
                raise RuntimeError(f'Published asset differs: {name}')
            request('DELETE', prefix + f'/releases/assets/{asset["id"]}'); asset = None
        if asset is None:
            print('Uploading ' + name, flush=True)
            asset = request('POST', prefix + f'/releases/{release["id"]}/assets?name=' + urllib.parse.quote(name), upload=path)
        checked = request('GET', prefix + f'/releases/assets/{asset["id"]}')
        if checked.get('digest') != 'sha256:' + hashes[name] or checked['size'] != path.stat().st_size or checked['state'] != 'uploaded':
            raise RuntimeError(f'Remote digest or size mismatch: {name}')
        print('Verified '+name,flush=True)
        return dict(name=name, sha256=hashes[name], size=checked['size'], url=checked['browser_download_url'])
    with ThreadPoolExecutor(max_workers=3) as pool:
        verified=list(pool.map(upload_asset,assets.items()))
    if release['draft']:
        release = request('PATCH', prefix + f'/releases/{release["id"]}', dict(draft=False, body=notes))
    release=request('GET',prefix+f'/releases/{release["id"]}')
    if release['draft'] or not release.get('published_at') or request('GET',prefix+'/commits/'+tag)['sha']!=args.target:
        raise RuntimeError('Release publication or target commit could not be verified')
    receipt = dict(version=args.version, commit=args.target, url=release['html_url'], assets=verified, status='published')
    (folder / 'github-release.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.cleanup:
        for path in assets.values():
            if path.suffix in {'.exe', '.apk', '.zip', '.aab'}:
                path.unlink()
    print(release['html_url'], flush=True)


if __name__ == '__main__':
    main()
