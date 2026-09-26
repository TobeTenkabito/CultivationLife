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
            assert len(config["extensions"]) == (6 if with_dlc else 0)
            request = urllib.request.Request(base + "/api/games", method="POST",
                data=json.dumps({"name": "打包验收", "spirit_root": "heavenly", "path": "dao", "seed": 134,
                                 "preset_id": "core"}).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=20) as response:
                game = json.load(response)
            assert "exchange_system" in game and game["natal_artifact"]["visible"]
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
            def post(operation, payload):
                request = urllib.request.Request(base + f"/api/games/{game['id']}/{operation}", method="POST",
                    data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.load(response)
            quote = post("merchant-preview", {"alliance_id": local["id"], "kind": "weapon", "material_tier": 1, "mold_id": "mirror"})
            assert quote["spec"]["mold"]["id"] == "mirror" and quote["commission_version"] == 2
            quote = post("merchant-preview", {"alliance_id": local["id"], "kind": "formation", "material_tier": 1})
            assert len(quote["spec"]["profile"]["metrics"]) == 6
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
            print(f"EXE verified: DLC={with_dlc}, version={config['base_game']['version']}, worlds=11")
        finally:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
            process.wait(timeout=10)
            time.sleep(.3)


if __name__ == "__main__":
    verify(False)
    verify(True)
