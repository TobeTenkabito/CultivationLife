"""Behavior and dependency-boundary regressions for the explicit engine ports."""

from __future__ import annotations

import ast
import builtins
import dis
import importlib
import inspect
import pkgutil
import random
import textwrap
from dataclasses import fields
from pathlib import Path
from types import CodeType, FunctionType, SimpleNamespace
from typing import get_type_hints
from unittest.mock import patch

import pytest

import cultivation_life.engine as engine_module
from cultivation_life.content_registry import REALMS, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.engine.actions import cultivation
from cultivation_life.engine.dependencies import CultivationActionDependencies
from cultivation_life.storage import SaveStore


def domain_functions():
    for info in pkgutil.walk_packages(engine_module.__path__, engine_module.__name__ + "."):
        if info.ispkg or info.name.rsplit(".", 1)[-1] in {"wiring", "dependencies", "ports"}:
            continue
        module = importlib.import_module(info.name)
        for member in vars(module).values():
            if isinstance(member, FunctionType) and member.__module__ == module.__name__:
                yield module, member


def loaded_globals(code: CodeType):
    for instruction in dis.get_instructions(code):
        if instruction.opname == "LOAD_GLOBAL":
            yield instruction.argval
    for value in code.co_consts:
        if isinstance(value, CodeType):
            yield from loaded_globals(value)


def test_domain_functions_resolve_imports_without_the_engine_namespace() -> None:
    checked = []
    for module, function in domain_functions():
        assert function.__globals__ is vars(module)
        assert "GameEngine" not in vars(module)
        for name in loaded_globals(function.__code__):
            assert name in vars(module) or hasattr(builtins, name), (module.__name__, function.__name__, name)
        get_type_hints(function)
        checked.append(function)
    assert checked


def test_forwarding_methods_do_not_shadow_their_implementation_modules() -> None:
    for member in vars(GameEngine).values():
        function = member.__func__ if isinstance(member, (staticmethod, classmethod)) else member
        if not isinstance(function, FunctionType):
            continue
        local_names = set(function.__code__.co_varnames)
        for node in ast.walk(ast.parse(textwrap.dedent(inspect.getsource(function)))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            target = node.func.value
            if isinstance(target, ast.Name) and inspect.ismodule(function.__globals__.get(target.id)):
                assert target.id not in local_names, (function.__name__, target.id)


def test_every_dependency_access_is_declared_in_its_contract() -> None:
    for module, function in domain_functions():
        if "deps" not in inspect.signature(function).parameters:
            continue
        contract = get_type_hints(function)["deps"]
        declared = {field.name for field in fields(contract)}
        declared.update(name for name, member in vars(contract).items() if isinstance(member, property))
        for node in ast.walk(ast.parse(inspect.getsource(function))):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "deps":
                assert node.attr in declared, (module.__name__, function.__name__, node.attr)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"getattr", "setattr"}:
                assert not any(isinstance(arg, ast.Name) and arg.id == "deps" for arg in node.args)


def test_a_domain_function_can_run_with_only_injected_collaborators() -> None:
    def unexpected(*args, **kwargs):
        raise AssertionError("This operation requested an unrelated dependency")

    arguments = {field.name: unexpected for field in fields(CultivationActionDependencies)}
    seen = []

    def describe(npc):
        seen.append(npc)
        return f"{npc.realm_index}:{npc.layer}"

    arguments["_npc_realm_name"] = describe
    deps = CultivationActionDependencies(**arguments)
    player = SimpleNamespace(name="隔离测试", age=30, lifespan=200, path="dao", world="human")

    assert cultivation._secret_art_realm_name(deps, player, 2, 3) == "2:3"
    assert len(seen) == 1
    assert seen[0].name == player.name
    assert seen[0].age == player.age


@pytest.fixture()
def engine_game(tmp_path: Path):
    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path / "saves")
    created = engine.create_game("依赖测试", "none", "dao", seed=67125)
    return engine, created["id"]


def test_action_callbacks_observe_overrides_after_engine_creation(engine_game) -> None:
    engine, game_id = engine_game
    start_age = engine.store.load(game_id).player.age
    with patch.object(engine, "_advance_world_year", return_value=False) as advance_world:
        engine.advance(game_id, "rest", 2)
    advance_world.assert_called_once()
    assert engine.store.load(game_id).player.age == start_age + 1


def test_load_uses_the_current_store_after_engine_creation(engine_game, tmp_path: Path) -> None:
    engine, game_id = engine_game
    game = engine.store.load(game_id)
    game.player.name = "替换后的存档"
    replacement = SaveStore(tmp_path / "replacement")
    replacement.save(game)
    engine.store = replacement

    assert engine.get_game(game_id)["player"]["name"] == "替换后的存档"


def test_class_helpers_preserve_subclass_dispatch_without_an_instance() -> None:
    class SevenfoldEngine(GameEngine):
        @staticmethod
        def _npc_lifespan_multiplier(path: str) -> int:
            return 7

    assert SevenfoldEngine._scale_npc_lifespan(20, "dao") == 140
    age, lifespan = SevenfoldEngine._roll_recruit_age_lifespan(1, "dao", random.Random(125))
    assert lifespan is not None and lifespan % 7 == 0
    assert age < lifespan


def test_bloodline_compatibility_hook_is_resolved_at_call_time(engine_game) -> None:
    engine, game_id = engine_game
    player = engine.store.load(game_id).player
    player.path = "monster"
    player.world = "monster_realm"
    player.realm_index = 8
    player.layer = REALMS[8].layers
    with patch.dict(WORLD_SYSTEMS["world_profiles"], {"nether": {"enabled": True}}):
        with patch.object(engine_module, "bloodline_content_available", return_value=True):
            assert engine._manual_breakthrough_kind(player) == "major"
        with patch.object(engine_module, "bloodline_content_available", return_value=False):
            assert engine._manual_breakthrough_kind(player) is None
