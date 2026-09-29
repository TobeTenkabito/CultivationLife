"""Run the built launcher in isolated folders, with and without optional DLC."""
import json
import runpy
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = runpy.run_path(str(ROOT / "cultivation_life/version.py"))["BASE_GAME_VERSION"]


def verify(with_dlc):
    with tempfile.TemporaryDirectory(prefix=f"exe-{VERSION}-", dir=ROOT / "build") as directory:
        folder = Path(directory).resolve()
        assert folder.is_relative_to((ROOT / "build").resolve())
        shutil.copy2(ROOT / "dist/launcher.exe", folder / "launcher.exe")
        if with_dlc:
            shutil.copytree(ROOT / "dlc", folder / "dlc")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen([str(folder / "launcher.exe"), "--port", str(port), "--no-browser"],
                                   cwd=folder, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(100):
                try:
                    with urllib.request.urlopen(base + "/api/config", timeout=1) as response:
                        config = json.load(response)
                    break
                except (OSError, TimeoutError):
                    time.sleep(.2)
            else:
                raise AssertionError("Packaged server did not start")
            assert config["base_game"]["version"] == VERSION
            assert len(config["worlds"]) == 11
            assert all(x["status"] == "loaded" for x in config["extensions"])
            assert len(config["extensions"]) == (len(list((ROOT/'dlc').glob('*/manifest.json'))) if with_dlc else 0)
            for theme in 'abcdef':
                with urllib.request.urlopen(base + f'/themes/{theme}.css', timeout=5) as response:
                    assert f'data-theme={theme}'.encode() in response.read()
            with urllib.request.urlopen(base + '/theme-manager.js', timeout=5) as response:
                assert b'window.GameThemes' in response.read()
            for asset in ['combat-plan-panel.js', 'doctrine-panel.js', 'doctrine-panel.css', 'theme-manager.js', 'index.html', 'ui-panels.js', 'save-transfer.js', 'save-transfer.css', 'theme-composition.js', 'themes/composition.css', 'themes/landscape.svg', 'family-panel.js', 'guixu-panel.js', 'app.js', 'map-directory.js', 'panels.css', 'buddhist-panel.js', 'buddhist-panel.css', 'buddhist-wish.js']:
                with urllib.request.urlopen(base + '/' + asset, timeout=5) as response:
                    assert response.read() == (ROOT / 'web' / asset).read_bytes()
            request = urllib.request.Request(base + '/api/ui-preferences', method='POST',
                data=b'{"theme":"f","reduced_motion":true}', headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request, timeout=5) as response:
                assert json.load(response) == {'theme':'f','reduced_motion':True}
            assert json.loads((folder / 'data/ui_preferences.json').read_text())['theme'] == 'f'
            with urllib.request.urlopen(base + '/api/ui-preferences', timeout=5) as response:
                assert json.load(response)['reduced_motion'] is True
            request = urllib.request.Request(base + "/api/games", method="POST",
                data=json.dumps({"name": "打包验收", "spirit_root": "heavenly", "path": "dao", "seed": 134,
                                 "preset_id": "core"}).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=20) as response:
                game = json.load(response)
            assert "exchange_system" in game and game["natal_artifact"]["visible"]
            def transfer(operation, payload):
                request = urllib.request.Request(base + '/api/save-transfer/' + operation, method='POST',
                    data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.load(response)
            snapshot_file = folder/'data/saves'/f"{game['id']}.json"
            original = json.loads(snapshot_file.read_bytes())
            exported = transfer('export', {'id':game['id']})
            preview = transfer('preview', {'payload':exported['payload']})
            assert preview['existing_hash']
            transfer('import', {'payload':exported['payload'], 'existing_hash':preview['existing_hash']})
            assert json.loads(snapshot_file.read_bytes()) == original
            assert next(i for i in game['player']['inventory'] if i['id']=='heroic_progeny_elixir')['quantity']==1
            assert game['family']['intrigue_enabled']==with_dlc
            assert game["tianji_artifacts"]["available"] == with_dlc
            assert len(game["merchant_system"]["alliances"]) == 3
            assert all(row['id'] != 'xuanji' for row in game['merchant_system']['alliances'])
            local = next(row for row in game["merchant_system"]["alliances"] if row["local_site"])
            request = urllib.request.Request(base + f"/api/games/{game['id']}/merchant-action", method="POST",
                data=json.dumps({"action": "join", "alliance_id": local["id"]}).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=20) as response:
                joined = json.load(response)
            assert joined["merchant_system"]["membership"]["alliance_id"] == local["id"]
            owned = next(row for row in joined['merchant_system']['alliances'] if row['member'])
            assert [row['world'] for row in owned['catalog']] == ['human']
            assert 'guixu_canghai_equipment_01' not in {row['id'] for row in owned['catalog'][0]['items']}
            assert 'heroic_progeny_elixir' not in {row['id'] for row in owned['catalog'][0]['items']}
            assert owned['catalog'][0]['weapon_tiers'] == [1,2,3,4,5]
            def post(operation, payload):
                request = urllib.request.Request(base + f"/api/games/{game['id']}/{operation}", method="POST",
                    data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.load(response)
            consumed = post('use-item', {'item_id':'heroic_progeny_elixir'})
            assert consumed['player']['guaranteed_progeny']
            assert not any(i['id']=='heroic_progeny_elixir' for i in consumed['player']['inventory'])
            quote = post("merchant-preview", {"alliance_id": local["id"], "kind": "weapon", "material_tier": 1, "mold_id": "mirror"})
            assert quote["spec"]["mold"]["id"] == "mirror" and quote["commission_version"] == 3
            quote = post("merchant-preview", {"alliance_id": local["id"], "kind": "formation", "material_tier": 1})
            assert len(quote["spec"]["profile"]["metrics"]) == 6
            quote = post('merchant-preview', {'alliance_id':local['id'], 'kind':'formation', 'stars':5,
                                              'material_tier':2, 'metric_maxima':{'kill':0}})
            assert quote['spec']['profile']['metrics']['kill'] == 0 and quote['spec']['spare_material_count'] == 4
            quote = post('merchant-preview', {'alliance_id':local['id'], 'kind':'weapon', 'stars':5, 'material_tier':2})
            assert quote['spec']['quality'] == 'legendary'
            try:
                post('merchant-preview', {'alliance_id':local['id'], 'kind':'weapon', 'source_world':'spirit'})
                raise AssertionError('Unlinked world must be rejected')
            except urllib.error.HTTPError as error:
                assert error.code == 400
            try:
                post("merchant-debug-hq", {"alliance_id": local["id"]})
                raise AssertionError("Debug endpoint must be disabled by default")
            except urllib.error.HTTPError as error:
                assert error.code == 404
            (folder / "game_config.txt").write_text("Debug=True\n", encoding="utf-8")
            debug = post("merchant-debug-hq", {"alliance_id": local["id"]})
            assert debug["merchant_system"]["membership"]["rank"] == 2
            with urllib.request.urlopen(base + "/merchant-commission-panel.js", timeout=5) as response:
                assert b"MerchantCommissionForm" in response.read()
            with urllib.request.urlopen(base + "/merchant-panel.js", timeout=5) as response:
                assert b"merchant-progress-log" in response.read()
            with urllib.request.urlopen(base + '/style.css', timeout=5) as response:
                assert b'button, input[type="button"], input[type="submit"]' in response.read()
            with urllib.request.urlopen(base + "/app.js", timeout=5) as response:
                assert b"function renderExchange" in response.read()
            with urllib.request.urlopen(base + '/map-directory.js', timeout=5) as response:
                assert b'window.MapDirectory' in response.read()
            assert all('境界序号' not in row.get('warning', '') for row in game['map']['locations'])
            assert any(row.get('factions') for row in game['map']['locations'])
            assert 'routes' in game['world_travel']
            request = urllib.request.Request(base + '/api/games', method='POST',
                data=json.dumps({'name':'剑诀验收','preset_id':'nascent','seed':1410}).encode(),
                headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request, timeout=20) as response:
                nascent = json.load(response)
            sword = next(row for row in nascent['player']['known_techniques'] if row['id']=='TECH_COMMON_GUI')
            assert sword['base_combat_bonus']==5000 and sword['growth_name']=='战斗'
            assert sword['next_level_gains']['combat_bonus']>0
            request = urllib.request.Request(base + '/api/games', method='POST',
                data=json.dumps({'name':'照尘验收','spirit_root':'supreme_wood','path':'buddhist','seed':1420}).encode(),
                headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request, timeout=20) as response:
                buddhist = json.load(response)
            assert buddhist['buddhist_system']['available'] == with_dlc
            if with_dlc:
                assert len(buddhist['buddhist_system']['blessings']) == 6
            # Verify a base-game upper-world entry and content against the executable's own API.
            save_path = folder / 'data/saves' / f"{buddhist['id']}.json"
            saved = json.loads(save_path.read_text(encoding='utf-8'))
            map_worlds = json.loads((ROOT/'content/maps.json').read_text(encoding='utf-8'))['worlds']
            saved['player'].update(world='hell', location_id=map_worlds['hell']['default'], realm_index=8, layer=9,
                                   opportunity=1e12, hp=1e12, mp=1e12)
            saved['pending_event'] = None
            save_path.write_text(json.dumps(saved, ensure_ascii=False), encoding='utf-8')
            request = urllib.request.Request(base + f"/api/games/{buddhist['id']}/celestial-ascension", method='POST',
                                             data=b'{}', headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request, timeout=20) as response:
                ascended = json.load(response)
            trial_saved = json.loads(save_path.read_text(encoding='utf-8'))
            assert trial_saved['active_trial']['destination'] == 'reincarnation'
            assert trial_saved['active_trial']['event_ids'][0].startswith('EVT_BUDDHIST_' if with_dlc else 'EVT_REINCARNATION_')
            trial_saved['active_trial'] = None; trial_saved['pending_event'] = None
            trial_saved['player'].update(world='reincarnation', location_id='reincarnation_well', realm_index=9, layer=1)
            save_path.write_text(json.dumps(trial_saved, ensure_ascii=False), encoding='utf-8')
            with urllib.request.urlopen(base + f"/api/games/{buddhist['id']}", timeout=20) as response:
                upper = json.load(response)
            assert len(upper['map']['locations']) == 28
            assert any(row.get('factions') for row in upper['map']['locations'])
            assert upper['buddhist_system']['available'] == with_dlc
            request = urllib.request.Request(base + '/api/games', method='POST',
                data=json.dumps({'name':'仙躯打包验收','preset_id':'true_immortal','seed':1460}).encode(),
                headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request, timeout=20) as response:
                immortal = json.load(response)
            assert immortal['player']['time_unit_years'] == 100
            assert immortal['aperture']['current'] == 300
            assert immortal['player']['body_training'] == 100
            assert immortal['map']['teleport']['arrays']
            assert len(immortal['doctrines']['veins']['names']) == 27
            assert immortal['player']['opportunity_unbounded']
            assert 'immortal_traces' in immortal['player']
            assert set(immortal['player']['intrinsic_resources']) == {'hp','mp'}
            assert immortal['doctrines']['veins']['total'] == 27
            assert immortal['doctrines']['veins']['trace_chance'] == .07
            assert immortal['doctrines']['immortal_body']['required_training'] == 100
            assert immortal['doctrines']['immortal_body']['golden_light_level'] == 20
            assert len(immortal['doctrines']['immortal_body']['manuals']) >= 1
            print(f"EXE verified: DLC={with_dlc}, version={config['base_game']['version']}, worlds=11")
        finally:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
            process.wait(timeout=10)
            time.sleep(.3)


if __name__ == "__main__":
    verify(False)
    verify(True)
