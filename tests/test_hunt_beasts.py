"""Configured hunt names resolve to shipped species-specific painted actors."""
import json
from pathlib import Path
from PIL import Image
from cultivation_life.combat_visuals import HUNT_BEAST_ASSETS, beast_asset, beast_kind
from cultivation_life.content_registry import ACTIONS
from cultivation_life.visual_assets import public_catalog

ROOT = Path(__file__).resolve().parents[1]


def test_authoritative_hunt_pool_has_exactly_one_specific_actor_per_name():
    names = ACTIONS['hunt_beast']['combat']['target_names']
    assert len(names) == len(set(names)) == 4
    assert set(names) == set(HUNT_BEAST_ASSETS)
    actors = [beast_asset(name) for name in names]
    assert len(set(actors)) == 4
    public = public_catalog(ROOT, [])['assets']['base.hunt_beasts_manifest']
    assert set(public['combat_actors']) == set(actors) and public['requires'] == []
    assert beast_asset('陌生巨鹰') == beast_kind('陌生巨鹰') == 'avian'
    assert beast_asset('陌生石猿') == beast_kind('陌生石猿')


def test_hunt_clips_keep_original_contact_clock_and_valid_alpha_bounds():
    manifest = json.loads((ROOT/'web/assets/pixel/hunt-beasts/manifest.json').read_text(encoding='utf8'))
    base = json.loads((ROOT/'web/assets/pixel/combat/manifest.json').read_text(encoding='utf8'))
    for name, ident in HUNT_BEAST_ASSETS.items():
        actor = manifest['actors'][ident]
        assert actor['name'] == name and actor['creature'] and actor['role'] == 'npc'
        assert actor['attack_action'] in base['actions']
        for mode, clip in actor['animations'].items():
            assert clip['duration'] == base['actors'][actor['beast_style']]['animations'][mode]['duration']
            assert len(clip['rects']) == len(clip['poses']) == clip['frames']
            with Image.open(ROOT/'web'/clip['sheet'].lstrip('/')) as im:
                assert im.mode == 'RGBA' and im.getchannel('A').getextrema()[0] == 0
                assert max(im.size) <= 2048
                for rect, pose in zip(clip['rects'],clip['poses']):
                    x,y,w,h,ox,oy = rect
                    assert 0 <= x < x+w <= im.width and 0 <= y < y+h <= im.height
                    assert 0 < ox < ox+w < 384 and 0 < oy < oy+h < 384
                    assert pose['anchor'] == [192,320]
                    assert im.crop((x,y,x+w,y+h)).getbbox()
        assert actor['animations']['defeat']['poses'][-1]['pose'] == 'down'
        assert len({p['pose'] for p in actor['animations']['attack']['poses']}) >= 4
