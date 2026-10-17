"""Record real quick starts, including selector variants, before balance edits."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--all-dlc',action='store_true')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='quick-calibration-') as directory:
        app=ROOT if args.all_dlc else Path(directory)/'base'
        if not args.all_dlc:
            shutil.copytree(ROOT/'content',app/'content')
            os.environ['CULTIVATION_APP_ROOT']=str(app)
        from cultivation_life.engine import GameEngine
        from cultivation_life.content_registry import WORLD_SYSTEMS
        from cultivation_life.rules import combat_power,expected_combat_power
        from scripts.release_evidence import inputs_digest
        engine=GameEngine(app,Path(directory)/'saves')
        rows=[]
        for preset in WORLD_SYSTEMS['quick_start_presets']:
            if not preset.get('enabled'):continue
            paths=list(preset['path_presets']) if preset.get('select_path') else [preset['path']]
            for path in paths:
                made=engine.create_game('快速开局数值样本','supreme_metal',path,2151,preset_id=preset['id'],
                    monster_species_id=next(iter(WORLD_SYSTEMS['monster_species'])) if path=='monster' else None)
                game=engine._load(made['id'])
                p=game.player
                row=dict(preset=preset['id'],selected_path=path,path=p.path,world=p.world,root=p.spirit_root,
                    rank=p.realm_index,layer=p.layer,power=combat_power(p),standard=expected_combat_power(p.realm_index,p.layer),
                    combat_arts=[dict(id=t.id,level=t.level) for t in p.combat_techniques],player=p.to_dict())
                rows.append(row)
                print(json.dumps({k:v for k,v in row.items() if k not in {'player','combat_arts'}},ensure_ascii=False),flush=True)
        report=dict(source_sha256=inputs_digest(ROOT),all_dlc=args.all_dlc,rows=rows)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
