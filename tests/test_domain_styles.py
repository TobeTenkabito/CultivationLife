"""Domain presentation eligibility, optional ownership, and read-only snapshots."""
import hashlib
import json
import random
from pathlib import Path
from unittest.mock import patch

import pytest
from cultivation_life import content_registry as registry
from cultivation_life import domain_styles as styles
from cultivation_life.ui_preferences import load_ui_preferences, write_ui_preferences

ROOT = Path(__file__).resolve().parents[1]
BASE = dict(outline='mist', pattern='mist', palette='#89abcd', control='rings', density=65)
PATHS = {'dao': 13, 'demonic': 18, 'monster': 18, 'ghost': 18, 'confucian': 14, 'buddhist': 14}


@pytest.mark.parametrize('path,count', PATHS.items())
def test_only_own_path_is_writable(path, count, tmp_path):
    choices = styles.available(path)
    assert len(choices) == count
    allowed = {r['id'] for r in choices}
    rng = random.getstate()
    for row in styles.catalog():
        value = BASE | dict(outline=row['id'], pattern=row['id'])
        if row['id'] in allowed:
            write_ui_preferences(tmp_path, {'voisinage_appearance': value}, character_path=path)
        else:
            before = (tmp_path/'data/ui_preferences.json').read_bytes()
            with pytest.raises(ValueError):
                write_ui_preferences(tmp_path, {'voisinage_appearance': value}, character_path=path)
            assert (tmp_path/'data/ui_preferences.json').read_bytes() == before
    assert random.getstate() == rng


@pytest.mark.parametrize('package,path,style', [
    ('asura-manifestation', 'demonic', 'asura-prison'),
    ('monster-bloodlines', 'monster', 'monster-origin'),
    ('ghost-reincarnation', 'ghost', 'ghost-rebirth')])
def test_disabled_package_preserves_preference_but_rejects_submission(tmp_path, package, path, style):
    selected = BASE | dict(outline=style, pattern=style)
    write_ui_preferences(tmp_path, {'voisinage_appearance': selected}, character_path=path)
    owner = 'official.'+package
    disabled = [r for r in registry.EXTENSION_REPORT if r['id'] != owner]
    before = (tmp_path/'data/ui_preferences.json').read_bytes()
    with patch.object(registry, 'EXTENSION_REPORT', disabled):
        assert len(styles.available(path)) == 15
        assert not any(r.get('owner') == owner for r in styles.catalog())
        assert load_ui_preferences(tmp_path)['voisinage_appearance'] == selected
        assert styles.project(selected, path) == BASE
        with pytest.raises(ValueError):
            write_ui_preferences(tmp_path, {'voisinage_appearance': selected}, character_path=path)
    assert (tmp_path/'data/ui_preferences.json').read_bytes() == before
    assert styles.project(selected, path) == selected


def test_declarations_are_unique_owned_and_content_matches_registry():
    rows = styles.catalog()
    assert len(rows) == len({r['id'] for r in rows}) == 30
    assert len(styles.available()) == 13
    for package in ['asura-manifestation', 'monster-bloodlines', 'ghost-reincarnation']:
        root = ROOT/'dlc'/package/'assets/visual'
        row = json.loads((root/'registry.json').read_text(encoding='utf8'))['assets'][package+'.domain_styles']
        data = (root/'domain-styles.json').read_bytes()
        assert row['sha256'] == hashlib.sha256(data).hexdigest()
        assert row['requires'] == ['official.'+package]
        assert row['domain_styles'] == json.loads(data)['styles']


def test_prison_scene_is_owned_registered_and_bounded():
    from cultivation_life.visual_assets import public_catalog, extension_asset
    scene = next(r for r in styles.catalog() if r['id'] == 'asura-prison')['scene']
    assets = public_catalog(ROOT, registry.EXTENSION_REPORT)['assets']
    row = assets['asura-manifestation.domain_prison']
    assert row['domain_art'] and row['requires'] == ['official.asura-manifestation']
    assert all(row[k] == scene[k] for k in ['file', 'size', 'sha256'])
    assert scene['size'] == [1024, 466] and scene['ink'] is True
    assert 'view' not in scene  # The tracing already contains only the upper composition.
    path = extension_asset(ROOT, ROOT, registry.EXTENSION_REPORT, scene['file'])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == scene['sha256']
    from PIL import Image
    alpha = Image.open(path).getchannel('A').histogram()
    assert alpha[0] / sum(alpha) > .8  # No architectural panels or landscape fill.


def test_all_thirty_domains_have_owned_transparent_outline_art():
    from PIL import Image
    from cultivation_life.visual_assets import public_catalog, extension_asset
    assets=public_catalog(ROOT,registry.EXTENSION_REPORT)['assets']
    total=0
    for style in styles.catalog():
        scene=style['scene']
        assert scene['ink'] is True
        row=next(r for r in assets.values() if r.get('file')==scene['file'])
        assert row['domain_art'] and row['sha256']==scene['sha256']
        if style.get('owner'):
            assert row['requires']==[style['owner']]
            path=extension_asset(ROOT,ROOT,registry.EXTENSION_REPORT,scene['file'])
        else:
            assert row['requires']==[] and scene['file'].startswith('/assets/pixel/domains/')
            path=ROOT/'web'/scene['file'].lstrip('/')
        assert hashlib.sha256(path.read_bytes()).hexdigest()==scene['sha256']
        image=Image.open(path)
        assert image.mode=='RGBA' and list(image.size)==scene['size']
        alpha=image.getchannel('A').histogram()
        assert .60<alpha[0]/sum(alpha)<.997,style['id']
        total+=image.width*image.height*4
    assert total<32*1024*1024


@pytest.mark.parametrize('owner', ['asura-manifestation','buddhist-dharma','ghost-reincarnation','guixu-tide',
    'intrigue-coalitions','monster-bloodlines','monster-civilizations','sage-way','tianji-artifacts','trial-sites'])
def test_each_package_owns_one_control_and_disabling_rejects_it(tmp_path, owner):
    package = 'official.'+owner
    rows = [r for r in styles.controls(all_paths=True) if r.get('owner') == package]
    assert len(rows) == 1
    row = rows[0]; path = row.get('path') or 'dao'
    selected = BASE | {'control':row['id']}
    write_ui_preferences(tmp_path, {'voisinage_appearance':selected}, character_path=path)
    if row.get('path'):
        with pytest.raises(ValueError):
            write_ui_preferences(tmp_path, {'voisinage_appearance':selected}, character_path='dao')
    with patch.object(registry, 'EXTENSION_REPORT', [r for r in registry.EXTENSION_REPORT if r['id'] != package]):
        assert row['id'] not in {r['id'] for r in styles.controls(all_paths=True)}
        assert load_ui_preferences(tmp_path)['voisinage_appearance'] == selected
        assert styles.project(selected, path)['control'] == 'rings'
        with pytest.raises(ValueError):
            write_ui_preferences(tmp_path, {'voisinage_appearance':selected}, character_path=path)
    p = ROOT/'dlc'/owner/'assets/visual'
    asset=json.loads((p/'registry.json').read_text(encoding='utf8'))['assets'][owner+'.domain_controls']
    assert asset['domain_controls'] == rows
    assert asset['requires'] == [package]
    assert asset['sha256'] == hashlib.sha256((p/'domain-controls.json').read_bytes()).hexdigest()


def test_controls_without_optional_packages_remain_available_for_every_path():
    with patch.object(registry, 'EXTENSION_REPORT', []):
        for path in [None, *PATHS]:
            assert len(styles.controls(path)) == 10
            for row in styles.controls(path):
                styles.validate(BASE | {'control':row['id']}, path)


def test_snapshot_uses_actual_path_without_consuming_game_rng(tmp_path):
    from cultivation_life.engine import GameEngine
    from cultivation_life.combat_visuals import report_visuals
    engine = GameEngine(ROOT, tmp_path/'saves')
    identity = engine.create_game('域式验收', 'heavenly', 'dao', 73, preset_id='core')['id']
    game = engine.store.load(identity)
    write_ui_preferences(tmp_path, {'voisinage_appearance': BASE | {'outline':'ghost-mist'}}, character_path='ghost')
    report = {'rounds':[{'voisinage':{'animation':{'fields':[{'owner':'player'}, {'owner':'enemy-0'}]}}}]}
    before = game.to_dict(); rng = random.getstate()
    with patch('cultivation_life.runtime.persistence_root', return_value=tmp_path), patch('secrets.choice', side_effect=lambda rows:rows[-1]):
        visual = report_visuals(game, {'path':'demonic'}, report, identity={'hero':'dao-male'})
    assert visual['domains']['player'] == BASE
    assert visual['domains']['enemy-0']['outline'] in {r['id'] for r in styles.available('demonic')}
    assert visual['domains']['enemy-0']['outline'] not in {r['id'] for r in styles.available('dao')}
    report['visual'] = visual
    assert report_visuals(game, {'path':'ghost'}, report, identity={'hero':'dao-male'})['domains'] == visual['domains']
    assert game.to_dict() == before and random.getstate() == rng
