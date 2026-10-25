"""Promote remaining approved actions and assemble the isolated DLC registry."""
from pathlib import Path
from PIL import Image
from scripts.prepare_monster_static_assets import read, write, sha, OWNER
from scripts import prepare_monster_flora_assets as packing

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'dlc/monster-bloodlines/assets/visual'


def promote_actions(species, date):
    out = BASE/species
    data = read(out/'manifest.json')
    recipe = read(ROOT/'scripts/monster_static_sources.json')['species'][species]
    identities = {(r['node'], r['gender']): r['identity'] for r in recipe['sources']}
    design = ROOT/f'design/{species}-combat-alpha4-{date}'
    source = read(design/'manifest.json')
    assets = read(out/'registry.json')['assets']
    provenance = read(out/'provenance.json')
    provenance['sources'] = [r for r in provenance['sources'] if r.get('kind') != 'actions']
    url = f'/extension-assets/{OWNER}/visual/{species}/'
    packing.URL = url
    actors = {}
    for a in source['actors'].values():
        identity = identities[a['node'], a['gender']]
        path = design/a['sheet']
        assert sha(path) == a['sha256']
        original = design/a['source']['file']
        assert sha(original) == a['source']['sha256']
        atlas = Image.open(path).convert('RGBA')
        frames = [atlas.crop((i%4*384, i//4*288, i%4*384+384, i//4*288+288)) for i in range(a['unique_frames'])]
        packed = packing.pack(frames, out/f'{identity}-actions.png')
        animations = {mode: dict(packed, rects=[packed['rects'][i] for i in clip['frames']],
                      frames=len(clip['frames']), poses=clip['poses'], duration=clip['duration'],
                      facing=1, cell=[384,288], body_sample_fps=0 if a['beast'] else 10)
                      for mode, clip in a['animations'].items()}
        attack = species+'_spell'
        animations[attack] = animations['attack']
        box = frames[2].getbbox()
        release = [box[0]+round((box[2]-box[0])*.8), box[1]+round((box[3]-box[1])*.35)] if a['beast'] else [235,152]
        actors[identity] = dict(name=a['name'], role='hero', faction=species, creature=a['beast'],
            sex=None if a['gender']=='shared' else a['gender'], cell=[384,288], anchor=[192,256],
            attack_action=attack, domain_action='idle' if a['beast'] else 'domain', release_point=release,
            energy_color=a['colors'][0], hit_offset=[25,-65] if a['beast'] else [23,-85],
            guard_shape=dict(cx=0,cy=-66,rx=98,ry=78) if a['beast'] else dict(cx=4,cy=-86,rx=70,ry=94),
            animations=animations)
        assets[identity+'.actions'] = dict(file=packed['sheet'], size=packed['size'], sha256=packed['sha256'], requires=[OWNER])
        provenance['sources'].append(dict(kind='actions',identity=identity,file=original.relative_to(ROOT).as_posix(),sha256=sha(original)))
    for rule in data['nodes'].values():
        if 'static' in rule: rule['combat'] = rule['static']
    data.update(actors=actors, scope='static_and_combat', fps=20,
                actions={species+'_spell':dict(name='血脉灵息',duration=4.0,contacts=[2.1])})
    write(out/'manifest.json', data)
    assets.pop(f'monster.{species}.static_manifest',None)
    assets[f'monster.{species}.combat_manifest'] = dict(file=url+'manifest.json',requires=[OWNER],sha256=sha(out/'manifest.json'))
    write(out/'registry.json',dict(assets=assets))
    provenance.update(combat_forms=len(actors),painted_keyposes=len(actors)*9,
                      animation_clips=sum(len(a['animations']) for a in source['actors'].values()))
    write(out/'provenance.json',provenance)


def assemble():
    package = ROOT/'dlc/monster-bloodlines/manifest.json'
    version = read(package)['version']
    assets = {}
    def appearance(identity, combat=None):
        return dict(static='actor.monster.'+identity, combat=combat or identity)
    for out in sorted(p for p in BASE.iterdir() if p.is_dir()):
        data = read(out/'manifest.json')
        species = out.name
        forms = []
        for node, rule in data['nodes'].items():
            form = dict(branch=node,min_realm=rule['realm'])
            if 'static' in rule:
                form['appearance'] = dict(static='actor.monster.'+rule['static'],combat=rule['combat'])
            elif 'variants' in rule:
                form['variants'] = {g:appearance(i) for g,i in rule['variants'].items()}
            elif 'history_variants' in rule:
                form['history_variants'] = {h:{g:appearance(i) for g,i in v.items()} for h,v in rule['history_variants'].items()}
            else:
                def variants(route):
                    genders = ['shared'] if data.get('gender_shared') else ['male','female']
                    return {g:appearance(f"{species}-{rule['stage']}-{route}-{g}") for g in genders}
                if rule.get('route'): form['variants'] = variants(rule['route'])
                else: form['history_variants'] = {h:variants(route) for h,route in data['history_routes'].items()}
            forms.append(form)
        data.update(version=version,realm_forms=forms)
        for actor in data['actors'].values(): actor['energy_effect'] = True
        write(out/'manifest.json',data)
        rows = read(out/'registry.json')['assets']
        entry = rows[f'monster.{species}.combat_manifest']
        entry.update(sha256=sha(out/'manifest.json'),combat_actors=list(data['actors']),appearance_key=species)
        write(out/'registry.json',dict(assets=rows))
        assets.update(rows)
    previous=read(BASE/'registry.json').get('assets',{}) if (BASE/'registry.json').exists() else {}
    assets.update({key:row for key,row in previous.items() if row.get('domain_styles') or row.get('domain_controls') or row.get('domain_art')})
    write(BASE/'registry.json',dict(schema_version=1,owner=OWNER,assets=assets))
    manifest = read(package)
    manifest['visual_registry'] = 'visual/registry.json'
    write(package,manifest)
    catalog = read(ROOT/'content/visual_assets.json')
    catalog['assets'] = {k:v for k,v in catalog['assets'].items() if OWNER not in v.get('requires',[])}
    write(ROOT/'content/visual_assets.json',catalog)
    print(f'{len(assets)} optional assets registered in DLC; core has {len(catalog["assets"])} declarations')


def main():
    promote_actions('avian','20261023')
    promote_actions('ape','20261024')
    assemble()


if __name__ == '__main__': main()
