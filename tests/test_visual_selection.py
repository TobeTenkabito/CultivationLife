"""Selection policy has no combat, character, DLC, file, or RNG dependency."""
import copy
import random

import pytest

from cultivation_life.visual_selection import select_assets


def test_unused_then_least_used_with_stable_preference():
    assert select_assets([['a', 'b']] * 5) == ['a', 'b', 'a', 'b', 'a']


def test_existing_stage_reservations_and_inputs_unchanged():
    pools, used = [['a', 'b'], ['a', 'b', 'c']], ['a', 'a', 'b']
    before = copy.deepcopy((pools, used))
    assert select_assets(pools, used_assets=used) == ['b', 'c']
    assert (pools, used) == before


def test_no_global_or_random_state_and_reentrant_new_scope():
    state = random.getstate()
    assert select_assets([['a', 'b']]) == select_assets([['a', 'b']]) == ['a']
    assert random.getstate() == state


def test_caller_legality_is_never_relaxed_for_uniqueness():
    assert select_assets([['a'], ['a'], ['b'], [], ['b']]) == ['a', 'a', 'b', None, 'b']
    assert select_assets([[]], used_assets=['forbidden']) == [None]


def test_duplicates_do_not_add_weight_and_ids_have_no_domain_semantics():
    assert select_assets([['scenery:2', 'scenery:2', 'icon:1']] * 3) == ['scenery:2', 'icon:1', 'scenery:2']
    assert select_assets((pool for pool in [('portrait-x',), ('portrait-y',)])) == ['portrait-x', 'portrait-y']


@pytest.mark.parametrize('pool,exception', [('not-a-pool', TypeError), ([''], ValueError), ([None], ValueError)])
def test_malformed_pools_are_not_silently_reinterpreted(pool, exception):
    with pytest.raises(exception):
        select_assets([pool])
