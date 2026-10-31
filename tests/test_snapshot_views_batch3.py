"""Snapshot isolation and unchanged decode/preparation boundaries."""
import ast
import copy
from collections import defaultdict
import gc
import hashlib
import json
from pathlib import Path
import random
from types import MappingProxyType, SimpleNamespace
import weakref

import pytest

from cultivation_life.snapshot_copy import copy_plain_data

ROOT = Path(__file__).resolve().parents[1]


def test_decode_and_view_algorithms_change_only_the_copy_implementation():
    fixture = ROOT/'tests/fixtures/snapshot_boundaries_332.json'
    assert hashlib.sha256(fixture.read_bytes().replace(b'\r\n', b'\n')).hexdigest() == 'f8183fb0638fde5e77cb7d8dea8b13724a2bac95de36e69055e52d2cb6d7faf4'
    expected = json.loads(fixture.read_text(encoding='utf-8'))
    actual = {}
    class OriginalCalls(ast.NodeTransformer):
        def visit_Call(self, node):
            self.generic_visit(node)
            if isinstance(node.func, ast.Name) and node.func.id == 'copy_plain_data':
                node.func = ast.Attribute(value=ast.Name(id='copy', ctx=ast.Load()), attr='deepcopy', ctx=ast.Load())
            return node
    for filename in {key.split(':')[0] for key in expected}:
        tree = ast.parse((ROOT/filename).read_text(encoding='utf-8'))
        for node in tree.body:
            methods = [(node.name+'.'+method.name, method) for method in node.body if isinstance(method, ast.FunctionDef)] if isinstance(node, ast.ClassDef) else [(getattr(node, 'name', ''), node)]
            for name, method in methods:
                key = filename+':'+name
                if key in expected:
                    method = OriginalCalls().visit(method)
                    actual[key] = hashlib.sha256(ast.dump(method, include_attributes=False).encode()).hexdigest()
    assert actual == expected


def test_plain_snapshots_match_deepcopy_for_random_documents():
    rng = random.Random(333)
    def tree(depth):
        if not depth or rng.randrange(3) == 0:
            return rng.choice([None, True, False, 0, -91, 1.25, '玩家文本', b'bytes'])
        if rng.randrange(2):
            return [tree(depth-1) for _ in range(rng.randrange(6))]
        return {rng.choice(['name', 'id', 'item', 7, None, (1, 2)]): tree(depth-1)
                for _ in range(rng.randrange(6))}
    for _ in range(600):
        source = tree(5)
        expected = copy.deepcopy(source)
        actual = copy_plain_data(source)
        assert actual == expected and type(actual) is type(expected)
        if isinstance(source, (list, dict)):
            assert actual is not source
            actual.clear()
            assert source == expected


def test_aliases_cycles_and_tuple_links_retain_independent_ownership():
    shared = {'nested': [1, 2]}
    source = [shared, shared]
    source.append(source)
    source.append((shared, source))
    actual = copy_plain_data(source)
    assert actual[0] is actual[1] and actual[2] is actual
    assert actual[3][0] is actual[0] and actual[3][1] is actual
    actual[0]['nested'].append(3)
    assert shared['nested'] == [1, 2]
    assert copy_plain_data(source)[0]['nested'] == [1, 2]


def test_custom_types_and_keys_keep_standard_deepcopy_hooks():
    class Key:
        def __deepcopy__(self, memo):
            clone = Key()
            memo[id(self)] = clone
            return clone
    class List(list):
        def __deepcopy__(self, memo):
            result = List(['custom-hook'])
            memo[id(self)] = result
            return result
    key = Key()
    source = {(key,): key, 'list': List([1]), 'map': defaultdict(list, a=[2]),
              'set': {1, 2}, 'namespace': SimpleNamespace(value=[3])}
    actual = copy_plain_data(source)
    copied_key = next(iter(actual))[0]
    assert copied_key is actual[(copied_key,)] and copied_key is not key
    assert type(actual['list']) is List and actual['list'] == ['custom-hook']
    assert actual['map'].default_factory is list and actual['map'] == {'a': [2]}
    assert actual['namespace'].value == [3] and actual['namespace'] is not source['namespace']
    assert actual['set'] == {1, 2} and actual['set'] is not source['set']


def test_extension_back_references_share_the_same_memo():
    class Link:
        def __deepcopy__(self, memo):
            return dict(back=copy.deepcopy(self.back, memo))
    link = Link()
    source = dict(link=link)
    link.back = source
    actual = copy_plain_data(source)
    assert actual['link']['back'] is actual


def test_extension_values_are_copied_before_dictionary_keys():
    calls = []
    class Value:
        def __init__(self, name):
            self.name = name
        def __deepcopy__(self, memo):
            calls.append(self.name)
            return self
    source = {Value('key'): Value('value')}
    copy.deepcopy(source)
    expected = list(calls)
    calls.clear()
    copy_plain_data(source)
    assert calls == expected == ['value', 'key']


def test_model_decode_preserves_source_and_independently_copied_fields(monkeypatch):
    from cultivation_life import models
    player = models.Player(name='快照隔离', spirit_root='none')
    game = models.GameState(id='snapshot-test', seed=333, player=player,
        created_at='baseline', updated_at='baseline',
        family_state={'extension': {'rows': [1, 2]}},
        ghost_parade={'extension': {'rows': [3, 4]}})
    source = game.to_dict()
    before = copy.deepcopy(source)
    actual = models.GameState.from_dict(source)
    with monkeypatch.context() as context:
        context.setattr(models, 'copy_plain_data', copy.deepcopy)
        expected = models.GameState.from_dict(source)
    assert actual.to_dict() == expected.to_dict()
    assert source == before
    actual.family_state['extension']['rows'].append(5)
    actual.ghost_parade['extension']['rows'].clear()
    assert source == before
    assert expected.family_state['extension']['rows'] == [1, 2]
    assert expected.ghost_parade['extension']['rows'] == [3, 4]


def test_source_ids_cannot_be_recycled_when_a_copy_hook_mutates_input():
    anchor = SimpleNamespace(value=1)
    class Hook:
        def __deepcopy__(self, memo):
            source.pop(0)
            # The source dict must remain alive, as stdlib deepcopy promises.
            assert any(type(row) is dict and row.get('anchor') is anchor
                       for row in gc.get_referrers(anchor))
            return 'hook'
    for copier in (copy.deepcopy, copy_plain_data):
        source = [{'anchor': anchor}, Hook()]
        actual = copier(source)
        assert actual[0]['anchor'] is not anchor and actual[1] == 'hook'


def test_temporary_memos_do_not_hold_sources_until_cyclic_gc():
    class Key(str):
        pass
    enabled = gc.isenabled()
    gc.disable()
    try:
        key = Key('ephemeral')
        reference = weakref.ref(key)
        source = {key: [1, 2]}
        result = copy_plain_data(source)
        assert next(iter(result)) is not key
        del source, key
        assert reference() is None
    finally:
        if enabled:
            gc.enable()


@pytest.mark.parametrize('source', [MappingProxyType({'x': 1}), iter([1, 2])])
def test_unsupported_and_extension_values_follow_stdlib(source):
    try:
        expected = copy.deepcopy(source)
    except Exception as error:
        with pytest.raises(type(error)):
            copy_plain_data(source)
    else:
        actual = copy_plain_data(source)
        assert type(actual) is type(expected)
