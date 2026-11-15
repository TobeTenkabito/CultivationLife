"""Frozen clone contributions, evaluated against this battle's actual state."""


def contribute(battle,state,stats):
    for identity,values in state.get('clone_stats',{}).items():
        unit=battle.units.get(identity)
        if unit is None or unit.unit.side!='player' or not battle._available(identity):continue
        fraction=min(1.,max(0.,unit.vitality)/max(.001,unit.unit.integrity))
        for key,value in values.items():
            stats['player'][key]+=value*fraction
