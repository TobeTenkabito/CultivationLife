"""Read-only visual vocabulary and path eligibility; no gameplay state or RNG."""
import json
from functools import lru_cache


@lru_cache(maxsize=4)
def _core(path):
    return json.loads(path.read_text(encoding='utf8'))


def _catalog(group):
    from . import content_registry as registry
    from .visual_assets import public_catalog
    rows = list(_core(registry.default_content_root()/'domain_styles.json')[group])
    assets = public_catalog(registry.default_content_root().parent, registry.EXTENSION_REPORT,
                            registry.default_extension_root())['assets']
    seen = {r['id'] for r in rows}
    for asset in assets.values():
        for row in asset.get('domain_'+group, []):
            if row['id'] not in seen:
                rows.append(row)
                seen.add(row['id'])
    return rows


def catalog():
    return _catalog('styles')


def controls(path=None, *, all_paths=False):
    return [r for r in _catalog('controls') if all_paths or not r.get('path') or r['path'] == path]


def available(path=None):
    return [r for r in catalog() if not r.get('path') or r['path'] == path]


def project(settings, path=None):
    """Unavailable/foreign styles fall back at presentation, never rewrite saves."""
    result = dict(settings)
    allowed = {r['id'] for r in available(path)}
    for key in ('outline', 'pattern'):
        if result.get(key) not in allowed:
            result[key] = 'mist'
    if result.get('control') not in {r['id'] for r in controls(path)}:
        result['control'] = 'rings'
    return result


def validate(settings, path=None):
    projected = project(settings, path)
    if any(projected[key] != settings[key] for key in ('outline', 'pattern', 'control')):
        raise ValueError('该邻域样式不属于当前道途，或所需 DLC 未加载')
