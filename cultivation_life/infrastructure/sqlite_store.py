from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from ..kernel.model import EventEnvelope, SAVE_FORMAT_ID, SAVE_SCHEMA_VERSION, WorldState
from .migrations import migrate_snapshot


class ConcurrentWriteError(RuntimeError):
    pass


class SQLiteSaveStore:
    """Atomic snapshot store with an append-only domain-event journal."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Commit or roll back a unit of work and always release the file handle."""
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS games (
                    game_id TEXT PRIMARY KEY,
                    format_id TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    player_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS event_journal (
                    game_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at INTEGER NOT NULL,
                    event_json TEXT NOT NULL,
                    PRIMARY KEY (game_id, sequence),
                    FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE
                );
                """
            )

    def create(self, state: WorldState, events: list[EventEnvelope], *, player_name: str) -> int:
        if state.revision != 0:
            raise ValueError("新存档修订号必须为零")
        return self._write(state, events, player_name=player_name, expected_revision=None)

    def save(
        self,
        state: WorldState,
        events: list[EventEnvelope],
        *,
        player_name: str,
        expected_revision: int,
    ) -> int:
        return self._write(
            state,
            events,
            player_name=player_name,
            expected_revision=expected_revision,
        )

    def _write(
        self,
        state: WorldState,
        events: list[EventEnvelope],
        *,
        player_name: str,
        expected_revision: int | None,
    ) -> int:
        old_revision = state.revision
        new_revision = 1 if expected_revision is None else expected_revision + 1
        try:
            state.revision = new_revision
            snapshot = json.dumps(state.to_dict(), ensure_ascii=False, separators=(",", ":"))
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT revision FROM games WHERE game_id = ?", (state.game_id,)
                ).fetchone()
                if expected_revision is None:
                    if existing is not None:
                        raise ConcurrentWriteError("存档已经存在")
                    connection.execute(
                        """
                        INSERT INTO games (
                            game_id, format_id, schema_version, revision, player_name,
                            created_at, updated_at, snapshot_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            state.game_id,
                            SAVE_FORMAT_ID,
                            SAVE_SCHEMA_VERSION,
                            new_revision,
                            player_name,
                            state.created_at,
                            state.updated_at,
                            snapshot,
                        ),
                    )
                else:
                    if existing is None or int(existing["revision"]) != expected_revision:
                        actual = None if existing is None else int(existing["revision"])
                        raise ConcurrentWriteError(
                            f"存档已被其他操作修改：期望 {expected_revision}，实际 {actual}"
                        )
                    connection.execute(
                        """
                        UPDATE games
                        SET format_id = ?, schema_version = ?, revision = ?, player_name = ?,
                            updated_at = ?, snapshot_json = ?
                        WHERE game_id = ? AND revision = ?
                        """,
                        (
                            SAVE_FORMAT_ID,
                            SAVE_SCHEMA_VERSION,
                            new_revision,
                            player_name,
                            state.updated_at,
                            snapshot,
                            state.game_id,
                            expected_revision,
                        ),
                    )
                for event in events:
                    connection.execute(
                        """
                        INSERT INTO event_journal (
                            game_id, sequence, event_type, occurred_at, event_json
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            state.game_id,
                            event.sequence,
                            event.event_type,
                            event.occurred_at,
                            json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":")),
                        ),
                    )
            return new_revision
        except Exception:
            state.revision = old_revision
            raise

    def load(self, game_id: str) -> WorldState:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT format_id, schema_version, revision, snapshot_json FROM games WHERE game_id = ?",
                (game_id,),
            ).fetchone()
        if row is None:
            raise KeyError("存档不存在")
        if row["format_id"] != SAVE_FORMAT_ID:
            raise ValueError("存档格式不受支持")
        snapshot = migrate_snapshot(json.loads(str(row["snapshot_json"])))
        state = WorldState.from_dict(snapshot)
        if state.game_id != game_id or state.revision != int(row["revision"]):
            raise ValueError("存档索引与快照不一致")
        return state

    def list_games(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT game_id, player_name, revision, created_at, updated_at
                FROM games ORDER BY updated_at DESC, game_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def load_events(self, game_id: str, *, after_sequence: int = 0) -> list[EventEnvelope]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT event_json FROM event_journal
                WHERE game_id = ? AND sequence > ? ORDER BY sequence
                """,
                (game_id, after_sequence),
            ).fetchall()
        return [EventEnvelope.from_dict(json.loads(str(row["event_json"]))) for row in rows]
