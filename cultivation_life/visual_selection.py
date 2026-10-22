"""Pure, reusable selection policy for caller-filtered visual asset IDs."""
from collections import Counter
from collections.abc import Iterable, Sequence


def select_assets(candidate_pools: Iterable[Sequence[str]], *, used_assets: Iterable[str] = ()) -> list[str | None]:
    """Select in request order without relaxing any caller's legal pool.

    Pools are ordered by caller preference, not by this module's knowledge of
    gender, character type, DLC, or storage. Existing on-stage IDs are reserved.
    Prefer the first unused candidate; after exhaustion reuse the least-used
    legal ID, with candidate order breaking ties. Empty pools return None and
    never borrow an illegal asset. Inputs and global state remain untouched.
    """
    used = Counter(used_assets)
    selected = []
    for candidates in candidate_pools:
        if isinstance(candidates, str):
            raise TypeError('An asset pool must be a sequence of IDs, not one ID')
        pool = list(dict.fromkeys(candidates))
        if any(not isinstance(asset, str) or not asset for asset in pool):
            raise ValueError('Asset IDs must be nonempty strings')
        asset = next((item for item in pool if not used[item]), None)
        if asset is None and pool:
            asset = min(pool, key=lambda item: used[item])
        selected.append(asset)
        if asset is not None:
            used[asset] += 1
    return selected
