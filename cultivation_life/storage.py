from __future__ import annotations

import json
import os
import tempfile
import threading
import hashlib
from collections import OrderedDict
from dataclasses import dataclass
from weakref import WeakValueDictionary
from pathlib import Path

from .models import GameState
from .errors import NotFoundError
from .version import BASE_GAME_VERSION
from .save_schema import SAVE_SCHEMA_VERSION, migrate_document, migration_path, schema_version


@dataclass(frozen=True, slots=True)
class _SummaryEntry:
    digest: bytes
    payload: str | None


def _summary_facts(data):
    """Only list metadata, never a hydrated game or an authority for loading."""
    player = data['player']
    return dict(id=data['id'], name=player['name'], updated_at=data['updated_at'],
        game_version=data.get('last_saved_with_game_version', 'pre-1.0.0'),
        age=player.get('age', 0), realm_index=player.get('realm_index', 0),
        layer=player.get('layer', 1), world=player.get('world', 'human'),
        path=player.get('path', 'dao'), alive=player.get('alive', True),
        authored_count=len(data.get('authored_techniques', {}).get('own', {})),
        version=data.get('version'))


def _public_summary(facts, size, labels):
    realms, world_systems, path_names = labels
    incompatibility = None
    try:
        migration_path(schema_version({'version': facts['version']}))
    except ValueError as error:
        incompatibility = str(error)
    return dict(id=facts['id'], name=facts['name'],
        compatible=incompatibility is None, incompatibility=incompatibility,
        updated_at=facts['updated_at'], game_version=str(facts['game_version']),
        age=facts['age'], realm_index=facts['realm_index'], layer=facts['layer'],
        world=facts['world'], path=facts['path'], alive=facts['alive'], bytes=size,
        authored_count=facts['authored_count'],
        realm_name=realms[int(facts['realm_index'])].name,
        world_name=world_systems['world_names'].get(facts['world'], '未知界面'),
        path_name=path_names.get(facts['path'], '修行者'))


class SaveStore:
    _locks = WeakValueDictionary()
    _registry_lock = threading.Lock()
    _SUMMARY_ENTRIES = 1024
    _SUMMARY_ENTRY_BYTES = 16 * 1024
    _SUMMARY_TOTAL_BYTES = 1024 * 1024

    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._summary_index = OrderedDict()
        self._summary_bytes = 0
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

    def _discard_summary(self, name):
        entry = self._summary_index.pop(name, None)
        if entry is not None and entry.payload is not None:
            self._summary_bytes -= len(entry.payload)

    def _remember_summary(self, name, digest, payload):
        self._discard_summary(name)
        if payload is not None and len(payload) > self._SUMMARY_ENTRY_BYTES:
            return
        self._summary_index[name] = _SummaryEntry(digest, payload)
        self._summary_bytes += len(payload) if payload is not None else 0
        while (len(self._summary_index) > self._SUMMARY_ENTRIES
               or self._summary_bytes > self._SUMMARY_TOTAL_BYTES):
            self._discard_summary(next(iter(self._summary_index)))

    def _indexed_facts(self, name, raw):
        # Always hash actual bytes: timestamps/size alone miss same-size edits
        # with restored mtime, including ordinary in-place edits on Windows.
        digest = hashlib.sha256(raw).digest()
        entry = self._summary_index.get(name)
        if entry is not None and entry.digest == digest:
            self._summary_index.move_to_end(name)
            return json.loads(entry.payload) if entry.payload is not None else None
        try:
            # Decode explicitly, retaining the old UTF-8/BOM rejection behavior.
            facts = _summary_facts(json.loads(raw.decode('utf-8')))
        except (KeyError, TypeError, ValueError, IndexError):
            self._remember_summary(name, digest, None)
            return None
        # Small immutable JSON facts give every caller independent mutable
        # values too. Labels and schema eligibility are recalculated each time.
        payload = json.dumps(facts, ensure_ascii=True, separators=(',', ':'))
        self._remember_summary(name, digest, payload)
        return facts

    def list_games(self) -> list[dict]:
        # Preserve the original per-call resource binding, before taking the
        # directory lock. Cached facts never freeze labels or schema policy.
        from .content_registry import REALMS, WORLD_SYSTEMS, PATH_NAMES
        labels = (REALMS, WORLD_SYSTEMS, PATH_NAMES)
        with self.lock:
            paths = []
            for path in self.directory.glob('*.json'):
                try:
                    paths.append((path, path.stat().st_mtime))
                except FileNotFoundError:
                    continue
            present = {path.name for path, _ in paths}
            for name in set(self._summary_index) - present:
                self._discard_summary(name)
            games = []
            for path, _ in sorted(paths, key=lambda row: row[1], reverse=True):
                try:
                    raw = path.read_bytes()
                except FileNotFoundError:
                    self._discard_summary(path.name)
                    continue
                facts = self._indexed_facts(path.name, raw)
                if facts is not None:
                    try:
                        games.append(_public_summary(facts, len(raw), labels))
                    except (KeyError, TypeError, ValueError, IndexError):
                        continue
            return games
