"""Save-local population rules, separate from a world's cultivation ceiling."""


def generation_profile(rng, power_ceiling, cultivation_ceiling, cultivation_layer=9):
    """Resource, population and boundary caps are distinct, ordered ranks.

    Resources constrain the ordinary population, not the world's power. An
    exceptional cultivator can exceed local training by layers only, never by
    a major realm; each generated person has a 5% chance of this exception.
    """
    depleted = rng.random() < .12
    ordinary_ceiling = min(power_ceiling, cultivation_ceiling)
    population_ceiling = rng.randint(4, ordinary_ceiling - 1) if depleted and ordinary_ceiling > 4 else ordinary_ceiling
    return dict(version=1, abundance="barren" if depleted else "ordinary",
                npc_realm_ceiling=population_ceiling, npc_layer_ceiling=9,
                ordinary_realm_ceiling=population_ceiling,
                ordinary_layer_ceiling=9 if population_ceiling < cultivation_ceiling else cultivation_layer,
                above_cultivation_chance=0. if depleted or cultivation_layer >= 9 else .05,
                cultivation_multiplier=.35 if depleted else 1.,
                realm_weights=[round(1 / rank ** 1.4, 5) for rank in range(1, population_ceiling + 1)])


def initial_rank(rng, profile, index):
    cap = profile["npc_realm_ceiling"]
    ordinary_layer = profile.get("ordinary_layer_ceiling", 9)
    if ordinary_layer < 9 and rng.random() < profile.get("above_cultivation_chance", 0):
        return cap, rng.randint(ordinary_layer + 1, profile["npc_layer_ceiling"])
    # A world's leading cultivator anchors its actual initial maximum. The
    # remaining population is weighted toward junior cultivators.
    if index == 0:
        return cap, ordinary_layer
    rank = rng.choices(list(range(1, cap + 1)), weights=profile["realm_weights"])[0]
    return rank, rng.randint(1, ordinary_layer if rank == cap else 9)
