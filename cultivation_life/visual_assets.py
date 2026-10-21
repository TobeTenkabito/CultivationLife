"""Read-only asset ownership, independent of simulation and player save state."""
import json
from functools import lru_cache
from pathlib import Path

from .errors import NotFoundError


@lru_cache(maxsize=8)
def catalog(root: Path):
    path = root/'content/visual_assets.json'
    if not path.is_file():
        return dict(schema_version=1,assets={},items={},molds={},plants={},crafting_materials={},maps={})
    return json.loads(path.read_text(encoding='utf-8'))


def public_catalog(root: Path, extensions):
    loaded = {row['id'] for row in extensions if row.get('status') == 'loaded'}
    source = catalog(root)
    def allowed(row):
        url = row.get('file','')
        owner = url.split('/')[2] if url.startswith('/extension-assets/') else None
        return set(row.get('requires',[])) <= loaded and (owner is None or owner in loaded)
    assets = {key:value for key,value in source['assets'].items() if allowed(value)}
    result = dict(schema_version=1,assets=assets)
    result['items'] = {key:row['asset'] for key,row in source['items'].items() if allowed(row) and row['asset'] in assets}
    for group in ['molds','plants','crafting_materials']:
        result[group] = {key:value for key,value in source[group].items() if value in assets}
    result['maps'] = {key:value for key,value in source['maps'].items() if value['asset'] in assets}
    return result


def extension_asset(root: Path, extension_root: Path, extensions, url: str):
    entry = next((row for row in public_catalog(root,extensions)['assets'].values() if row['file'] == url),None)
    if not entry or not entry.get('requires'):
        raise NotFoundError('素材未安装或未启用')
    _,_,package_id,relative = url.split('/',3)
    for manifest in (extension_root/'dlc').glob('*/manifest.json'):
        if json.loads(manifest.read_text(encoding='utf-8')).get('id') != package_id:
            continue
        base = (manifest.parent/'assets').resolve()
        target = (base/relative).resolve()
        if target.is_relative_to(base) and target.is_file():
            return target
    raise NotFoundError('素材不存在')
