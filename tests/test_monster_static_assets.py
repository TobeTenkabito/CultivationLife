"""Static DLC art follows real bloodlines without changing combat or player state."""
import copy
import hashlib
import json
import random
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from cultivation_life import content_registry as registry
from cultivation_life.models import Player
from cultivation_life.monster_visuals import monster_appearance
from cultivation_life.visual_assets import public_catalog, extension_asset
from cultivation_life.errors import NotFoundError

ROOT = Path(__file__).resolve().parents[1]
RECIPE = json.loads((ROOT/'scripts/monster_static_sources.json').read_text(encoding='utf-8'))
CASES = [(species, row) for species, spec in RECIPE['species'].items() for row in spec['sources']]
OWNER = 'official.monster-bloodlines'


def player(species, node, gender='female', history=None):
    return Player(name='像素头像验收', spirit_root='heavenly', path='monster', gender=gender,
                  monster_species_id=species, monster_evolution_id=node,
                  monster_evolution_history=history or [node])


@pytest.mark.parametrize('species,row', CASES, ids=[row['identity'] for _, row in CASES])
def test_each_selected_original_has_runtime_assets_and_no_state_changes(species, row):
    p = player(species, row['node'], 'female' if row['gender']=='shared' else row['gender'])
    before, rng = copy.deepcopy(p.to_dict()), random.getstate()
    appearance = monster_appearance(p)
    assert appearance == dict(static='actor.monster.'+row['identity'], combat=row['identity'])
    assets = public_catalog(ROOT, registry.EXTENSION_REPORT)['assets']
    for kind, size in [('portrait', (128,128)), ('figure',(256,288)), ('thumbnail',(128,144))]:
        asset = assets[appearance['static']+'.'+kind]
        path = extension_asset(ROOT, ROOT, registry.EXTENSION_REPORT, asset['file'])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == asset['sha256']
        with Image.open(path) as im:
            assert im.mode == 'RGBA' and im.size == size
            box = im.getbbox()
            assert box and 0 < box[0] < box[2] < size[0] and 0 < box[1] < box[3] < size[1]
            assert len(set(im.getchannel('A').getdata())) > 2
        with pytest.raises(NotFoundError):
            extension_asset(ROOT, ROOT, [], asset['file'])
    assert p.to_dict() == before and random.getstate() == rng


@pytest.mark.parametrize('species', ['avian', 'ape'])
def test_retained_forms_use_only_valid_ancestry_and_actual_bloodline(species):
    data = json.loads((ROOT/f'dlc/monster-bloodlines/assets/visual/{species}/manifest.json').read_text(encoding='utf-8'))
    for node, rule in data['nodes'].items():
        p = player(species, node)
        p.world = 'human'; p.realm_index = 1  # Sealed display does not select young art.
        if 'history_variants' in rule:
            assert monster_appearance(p) is None
            p.monster_evolution_history = ['NOT_A_NODE', 'FOX_NINE_TAIL', node]
            assert monster_appearance(p) is None
            for ancestor, variants in rule['history_variants'].items():
                p.monster_evolution_history = [ancestor, node]
                assert monster_appearance(p)['static'] == 'actor.monster.'+variants['female']
        else:
            assert monster_appearance(p)
    p = player(species, species.upper()+'_NETHER_TRUE_1')
    assert monster_appearance(p) is None


@pytest.mark.parametrize('species', ['avian', 'ape'])
def test_disabled_dlc_and_borrowed_or_transformed_identity_fall_back(species):
    p = player(species, species.upper()+'_SPIRIT')
    with patch.object(registry, 'EXTENSION_REPORT', []):
        assert monster_appearance(p) is None
    for field, value in [('path','dao'), ('ghost_host_body',{'name':'宿身'}), ('ghost_attachment',{'id':'x'})]:
        other = copy.deepcopy(p); setattr(other, field, value)
        assert monster_appearance(other) is None
    p.transformation_loadouts = {None: {'active': ['shape']}}
    assert monster_appearance(p) is None
    assert not any(k.startswith(('actor.monster.avian-', 'actor.monster.ape-'))
                   for k in public_catalog(ROOT, [])['assets'])


def test_promoted_forms_use_their_own_combat_identity():
    from types import SimpleNamespace
    from cultivation_life.combat_visuals import combat_identity
    for species, row in CASES:
        gender = 'male' if row['gender']=='shared' else row['gender']
        p = player(species, row['node'], gender)
        game = SimpleNamespace(player=p, natal_artifact={}, encounter_npc_cache=[])
        # No NPC is invented for this identity-only projection.
        with patch('cultivation_life.combat_visuals.find_person', return_value=None):
            result = combat_identity(game, {'target_name':'验证对手', 'path':'dao', 'gender':'male'})
        assert result['hero'] == row['identity']
        assert result['teams']['hero'][0]['asset'] == row['identity']


def test_selected_revisions_are_the_current_repaired_originals():
    avian = {r['identity']:r for r in RECIPE['species']['avian']['sources']}
    for suffix in ['azure-sovereign-male','flame-sovereign-female','flame-sovereign-male']:
        assert avian['avian-nascent-'+suffix]['file'].endswith('-v2.png')
