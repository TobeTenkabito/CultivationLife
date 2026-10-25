"""Offline pixel export of the redesigned Asura protagonists; no runtime design dependency."""
import importlib.util
import json
from pathlib import Path

from PIL import Image
from scripts.prepare_monster_static_assets import paired_parts, read, write, sha
from scripts.prepare_monster_flora_assets import pack

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/asura-characters-20261025'
PACKAGE = ROOT / 'dlc/asura-manifestation'
OWNER = 'official.asura-manifestation'
VERSION = '1.3.0'
POSES = ['idle', 'gather', 'release', 'guard', 'brace', 'hit', 'stagger', 'kneel', 'down']


def main():
    spec = importlib.util.spec_from_file_location('asura_pose_tools', ROOT/'design/flora-combat-alpha4-20261024/prepare.py')
    motion = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(motion)
    out = PACKAGE / 'assets/visual/characters'
    out.mkdir(parents=True, exist_ok=True)
    url = f'/extension-assets/{OWNER}/visual/characters/'
    sources = read(DESIGN/'redesign-prompts.json')
    assets, actors, forms, provenance, preview = {}, {}, [], [], []
    clips = json.loads(json.dumps(motion.CLIPS))
    clips['attack']['name'] = '修罗煞印'
    for source in sources:
        ident = source['id']
        gender = ident.rsplit('-', 1)[1]
        static = 'actor.path.' + ident
        original = DESIGN / source['file']
        parts = paired_parts(original)
        for kind, size in [('portrait', (128, 128)), ('figure', (256, 288)), ('thumbnail', (128, 144))]:
            art = parts[1 if kind == 'portrait' else 0][0]
            scale = min((size[0]-12)/art.width, (size[1]-16)/art.height)
            art = art.resize((round(art.width*scale), round(art.height*scale)), Image.Resampling.NEAREST)
            canvas = Image.new('RGBA', size)
            canvas.paste(art, ((size[0]-art.width)//2, size[1]-8-art.height))
            target = out / f'{ident}-{kind}.png'
            canvas.save(target, optimize=True)
            assets[static+'.'+kind] = dict(file=url+target.name, size=list(size), sha256=sha(target), requires=[OWNER])
        action = DESIGN / source['actions_file']
        parts = motion.split_parts(action, 9, 3)
        scale = min(176/parts[0][0].height, 282/max(im.width for im, _ in parts), 180/max(im.height for im, _ in parts))
        frames, records = [], {}
        for pose, (art, box) in zip(POSES, parts):
            art = art.resize((round(art.width*scale), round(art.height*scale)), Image.Resampling.NEAREST)
            canvas = Image.new('RGBA', (384, 288))
            offset = (192-art.width//2, 256-art.height)
            canvas.paste(art, offset)
            target = DESIGN / 'poses' / ident / (pose+'.png')
            target.parent.mkdir(parents=True, exist_ok=True)
            canvas.save(target, optimize=True)
            frames.append(canvas)
            records[pose] = dict(source_rect=box, scale=scale, offset=offset, sha256=sha(target))
        packed = pack(frames, out/f'{ident}-actions.png')
        packed['sheet'] = url + f'{ident}-actions.png'
        groups = {}
        for mode, clip in clips.items():
            indices = [POSES.index(next(p for start, p in reversed(clip['keys']) if at/20 >= start))
                       for at in range(round(clip['duration']*20)+1)]
            groups[mode] = dict(packed, rects=[packed['rects'][i] for i in indices], frames=len(indices),
                               poses=[POSES[i] for i in indices], duration=clip['duration'], facing=1,
                               cell=[384, 288], body_sample_fps=10)
        groups['asura_spell'] = groups['attack']
        actors[ident] = dict(name=source['name'], role='hero', faction='demonic', creature=False, sex=gender,
                            cell=[384, 288], anchor=[192, 256], attack_action='asura_spell', domain_action='domain',
                            release_point=[235, 152], energy_color='#eaa18a', energy_effect=True,
                            hit_offset=[23, -85], guard_shape=dict(cx=4, cy=-86, rx=70, ry=94), animations=groups)
        forms.append(dict(path='demonic', race='human', gender=gender, role='hero', min_realm_index=9,
                          static=static, combat=ident))
        assets[ident+'.actions'] = dict(file=packed['sheet'], size=packed['size'], sha256=packed['sha256'], requires=[OWNER])
        provenance.append(dict(identity=ident, static_source=source['file'], static_sha256=sha(original),
                               actions_source=source['actions_file'], actions_sha256=sha(action), poses=records))
        preview.append(dict(id=ident, name=source['name'], static_file=source['file'], poses=records,
                            figure=f'../../dlc/asura-manifestation/assets/visual/characters/{ident}-figure.png',
                            portrait=f'../../dlc/asura-manifestation/assets/visual/characters/{ident}-portrait.png'))
    write(out/'manifest.json', dict(schema_version=1, owner=OWNER, version=VERSION, fps=20, actors=actors,
                                   actions=dict(asura_spell=dict(name='修罗煞印', duration=4, contacts=[2.1]))))
    assets['asura.character_manifest'] = dict(file=url+'manifest.json', sha256=sha(out/'manifest.json'), requires=[OWNER],
                                             combat_actors=list(actors), character_forms=forms)
    write(out.parent/'registry.json', dict(assets=assets))
    write(out/'provenance.json', dict(generator='OpenAI built-in image_gen',
          prompts='design/asura-characters-20261025/redesign-prompts.json', static_forms=2, painted_keyposes=18,
          animation_clips=14, export='nearest-neighbour, original alpha, common scale and foot anchor', sources=provenance))
    manifest = read(PACKAGE/'manifest.json')
    manifest.update(version=VERSION, visual_registry='visual/registry.json')
    write(PACKAGE/'manifest.json', manifest)
    data = dict(actors=preview, poses=POSES, clips=clips)
    write(DESIGN/'manifest.json', data)
    (DESIGN/'data.js').write_text('window.PathArt='+json.dumps(data, ensure_ascii=False)+';\n', encoding='utf-8')
    print('Asura DLC 1.3.0: 2 protagonists, 6 pixel static images, 18 keyposes, 14 animation clips')


if __name__ == '__main__':
    main()
