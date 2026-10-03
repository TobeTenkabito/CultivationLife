from __future__ import annotations

import json
import os
import tempfile
import threading
from weakref import WeakValueDictionary
from pathlib import Path

from .models import GameState
from .errors import NotFoundError
from .version import BASE_GAME_VERSION
from .save_schema import SAVE_SCHEMA_VERSION, migrate_document, migration_path, schema_version


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
        if type(game.version) is not int or game.version != SAVE_SCHEMA_VERSION:
            raise ValueError('只能保存当前结构版本的游戏状态')
        game.last_saved_with_game_version = BASE_GAME_VERSION
        self._write_document(game.id, game.to_dict())

    def _write_document(self, game_id: str, document: dict) -> None:
        """Atomically commit an already validated document, retaining extension fields."""
        path = self._path(game_id)
        data = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        with self.lock:
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.directory,
                                                 prefix=f'{game_id}.', suffix='.tmp', delete=False) as output:
                    temporary = Path(output.name)
                    output.write(data)
                temporary.replace(path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

    def load(self, game_id: str) -> GameState:
        path = self._path(game_id)
        with self.lock:
            if not path.exists():
                raise NotFoundError("存档不存在")
            original = json.loads(path.read_text(encoding="utf-8"))
            data = migrate_document(original)
            if data.get('id') != game_id:
                raise ValueError('存档编号与文件名不一致')
            game = GameState.from_dict(data)
            if data is not original:
                # Commit only after the full migration and model decode succeed.
                self._write_document(game_id, data)
            return game

    def delete(self, game_id: str) -> None:
        """Delete only the requested save; account achievements remain untouched."""
        path = self._path(game_id)
        with self.lock:
            try:
                path.unlink()
            except FileNotFoundError:
                raise NotFoundError("存档不存在") from None

    def list_games(self) -> list[dict]:
        from .content_registry import REALMS, WORLD_SYSTEMS, PATH_NAMES
        games: list[dict] = []
        for path in sorted(self.directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                migration_path(schema_version(data))
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
