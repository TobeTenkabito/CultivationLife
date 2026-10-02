from __future__ import annotations

import json
import os
import tempfile
import threading
from weakref import WeakValueDictionary
from pathlib import Path

from .models import GameState
from .version import BASE_GAME_VERSION


class SaveStore:
    _locks = WeakValueDictionary()
    _registry_lock = threading.Lock()

    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        with self._registry_lock:
            key = os.path.normcase(str(directory.resolve()))
            self.lock = self._locks.setdefault(key, threading.RLock())

    def _path(self, game_id: str) -> Path:
        if not game_id.replace("-", "").isalnum():
            raise ValueError("非法存档 ID")
        return self.directory / f"{game_id}.json"

    def save(self, game: GameState) -> None:
        game.last_saved_with_game_version = BASE_GAME_VERSION
        path = self._path(game.id)
        data = json.dumps(game.to_dict(), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        with self.lock:
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.directory,
                                                 prefix=f'{game.id}.', suffix='.tmp', delete=False) as output:
                    temporary = Path(output.name)
                    output.write(data)
                temporary.replace(path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

    def load(self, game_id: str) -> GameState:
        path = self._path(game_id)
        if not path.exists():
            raise KeyError("存档不存在")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") not in {2, 3, 4, 5}:
            raise ValueError("该存档属于旧版大更新前格式，请新建角色")
        return GameState.from_dict(data)

    def delete(self, game_id: str) -> None:
        """Delete only the requested save; account achievements remain untouched."""
        path = self._path(game_id)
        with self.lock:
            try:
                path.unlink()
            except FileNotFoundError:
                raise KeyError("存档不存在") from None

    def list_games(self) -> list[dict]:
        from .content_registry import REALMS, WORLD_SYSTEMS, PATH_NAMES
        games: list[dict] = []
        for path in sorted(self.directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("version") not in {2, 3, 4, 5}:
                    continue
                games.append({
                    "id": data["id"],
                    "name": data["player"]["name"],
                    "updated_at": data["updated_at"],
                    "game_version": str(data.get("last_saved_with_game_version", "pre-1.0.0")),
                    "age": data['player'].get('age', 0),
                    "realm_index": data['player'].get('realm_index', 0),
                    "layer": data['player'].get('layer', 1),
                    "world": data['player'].get('world', 'human'),
                    "path": data['player'].get('path', 'dao'),
                    "alive": data['player'].get('alive', True),
                    "bytes": path.stat().st_size,
                    "realm_name": REALMS[int(data['player'].get('realm_index', 0))].name,
                    "world_name": WORLD_SYSTEMS['world_names'].get(data['player'].get('world', 'human'), '未知界面'),
                    "path_name": PATH_NAMES.get(data['player'].get('path', 'dao'), '修行者'),
                })
            except (KeyError, TypeError, ValueError, IndexError):
                continue
        return games
