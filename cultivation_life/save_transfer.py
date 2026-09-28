"""Bounded, lossless portable snapshots. Encryption lives in Web Crypto, not Python."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
import threading
import uuid
import zlib

from .models import GameState
from .runtime import decode_rng
from .version import BASE_GAME_VERSION

MAX_RAW = 64 * 1024 * 1024
MAX_PACKED = 12 * 1024 * 1024
TRANSFER_LOCK = threading.RLock()


def _json(raw):
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError("存档存在重复字段")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("存档数值无效")))
    except (TypeError, UnicodeError, RecursionError, json.JSONDecodeError) as error:
        raise ValueError("存档数据无法解析") from error


def _validate(document):
    if not isinstance(document, dict) or document.get("format") != "fusheng-save" or document.get("format_version") != 1:
        raise ValueError("这不是支持的浮生问道存档码")
    version = document.get("game_version", "")
    if not isinstance(version, str) or not re.fullmatch(r"\d{1,4}\.\d{1,4}\.\d{1,4}", version):
        raise ValueError("存档版本无效")
    if tuple(map(int, version.split('.'))) > tuple(map(int, BASE_GAME_VERSION.split('.'))):
        raise ValueError("此存档来自更高版本，请先更新游戏")
    data = document.get("save")
    if not isinstance(data, dict) or data.get("version") not in {2, 3, 4, 5}:
        raise ValueError("不支持的存档结构")
    if not isinstance(data.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9-]{1,80}", data['id']):
        raise ValueError("存档编号无效")
    try:
        # Validation on a copy: don't erase dormant DLC fields or alter the RNG.
        state = GameState.from_dict(copy.deepcopy(data))
        if not isinstance(state.player.name, str) or not 1 <= len(state.player.name) <= 80:
            raise ValueError("角色名称无效")
        from .content_registry import REALMS, WORLD_SYSTEMS, PATH_NAMES
        rank = state.player.realm_index
        if type(rank) is not int or not 0 <= rank < len(REALMS):
            raise ValueError("角色境界无效")
        if type(state.player.layer) is not int or not 1 <= state.player.layer <= REALMS[rank].layers:
            raise ValueError("角色层数无效")
        if state.player.world not in WORLD_SYSTEMS['world_names'] or state.player.path not in PATH_NAMES:
            raise ValueError("角色界面或道统无效")
        import math
        for value in (state.player.age, state.player.hp, state.player.mp, state.player.opportunity):
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("角色数值无效")
        if not isinstance(document.get('extensions', []), list) or len(document.get('extensions', [])) > 256:
            raise ValueError("扩展列表无效")
        if not isinstance(state.seed, int) or not isinstance(state.rng_state, str) or len(state.rng_state) > 20_000:
            raise ValueError("天机数状态无效")
        decode_rng(state.seed, state.rng_state)
    except (KeyError, TypeError, AttributeError, RecursionError, OverflowError, SyntaxError, ValueError) as error:
        raise ValueError("存档结构损坏，无法恢复") from error
    return data


def export_snapshot(store, game_id, extensions=()):
    path = store._path(game_id)
    if not path.exists():
        raise KeyError("存档不存在")
    if path.stat().st_size > MAX_RAW:
        raise ValueError("此存档超过 64 MB 导出上限")
    original = path.read_bytes()
    data = _json(original)
    document = {"format": "fusheng-save", "format_version": 1, "game_version": BASE_GAME_VERSION,
                "extensions": [{"id": row.get('id'), "version": row.get('version')}
                               for row in extensions if row.get('status') == 'loaded'], "save": data}
    _validate(document)
    raw = json.dumps(document, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(raw) > MAX_RAW:
        raise ValueError("此存档超过 64 MB 导出上限")
    packed = zlib.compress(raw, 9)
    if len(packed) > MAX_PACKED:
        raise ValueError("此存档压缩后仍超过 12 MB 上限")
    return {"payload": base64.b64encode(packed).decode('ascii'), "name": data['player']['name'],
            "original_bytes": len(original), "packed_bytes": len(packed)}


def decode_snapshot(payload):
    if not isinstance(payload, str) or len(payload) > (MAX_PACKED + 2) // 3 * 4:
        raise ValueError("存档码过长")
    try:
        packed = base64.b64decode(payload, validate=True)
        inflater = zlib.decompressobj()
        raw = inflater.decompress(packed, MAX_RAW + 1)
        if len(raw) > MAX_RAW or inflater.unconsumed_tail:
            raise ValueError("解压后的存档超过 64 MB 上限")
        if not inflater.eof or inflater.unused_data:
            raise ValueError("存档码不完整或含多余数据")
    except (zlib.error, ValueError) as error:
        raise ValueError(f"存档解压失败：{error}") from error
    document = _json(raw)
    data = _validate(document)
    return document, data


def preview_snapshot(store, payload, extensions=()):
    document, data = decode_snapshot(payload)
    path = store._path(data['id'])
    existing = path.read_bytes() if path.exists() else None
    from .content_registry import WORLD_SYSTEMS, REALMS, PATH_NAMES
    player = data['player']
    rank = player.get('realm_index', 0)
    current = {row.get('id') for row in extensions if row.get('status') == 'loaded'}
    return {"id": data['id'], "name": player['name'], "age": player.get('age'),
            "realm": REALMS[rank].name if isinstance(rank, int) and 0 <= rank < len(REALMS) else "未知境界",
            "layer": player.get('layer'), "world": WORLD_SYSTEMS['world_names'].get(player.get('world'), '未知界面'),
            "path": PATH_NAMES.get(player.get('path'), '修行者'), "version": document['game_version'],
            "updated_at": data.get('updated_at'), "history_count": len(data.get('history', [])),
            "existing_hash": hashlib.sha256(existing).hexdigest() if existing is not None else None,
            "missing_extensions": [row['id'] for row in document.get('extensions', [])
                                   if isinstance(row, dict) and row.get('id') and row['id'] not in current]}


def import_snapshot(store, payload, expected_existing_hash):
    _, data = decode_snapshot(payload)
    raw = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    with TRANSFER_LOCK:
        path = store._path(data['id'])
        existing = path.read_bytes() if path.exists() else None
        actual_hash = hashlib.sha256(existing).hexdigest() if existing is not None else None
        if actual_hash != expected_existing_hash:
            raise ValueError("本机存档已发生变化，请重新预览后再导入")
        if existing is not None:
            backup = store.directory.parent / 'save-backups'
            backup.mkdir(parents=True, exist_ok=True)
            (backup / f"{data['id']}-{uuid.uuid4().hex}.json").write_bytes(existing)
        temporary = path.with_suffix(f'.{uuid.uuid4().hex}.tmp')
        try:
            temporary.write_bytes(raw)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return {"id": data['id'], "name": data['player']['name'], "replaced": existing is not None}
