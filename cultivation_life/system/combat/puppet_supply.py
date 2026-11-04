"""Pure per-attack funding: exactly one source, never refill an asset in combat."""


class PuppetSupply:
    def operating_attack(self,state):
        c=state.unit.capabilities
        own=c.operating_compatible and state.operating_energy is not None and state.operating_energy>=c.operating_cost>0
        immortal=c.force_tier>=2 and 'technique' not in state.restrictions
        if own and (not immortal or c.operating_tier>=2):
            return (2 if immortal else 1,'self',c.operating_cost)
        sponsor=self.units.get(c.attack_resource_owner)
        can_supply=(c.allow_sponsor and sponsor is not None and sponsor.fighting
                    and 'supply' not in sponsor.restrictions and 'supply' not in state.restrictions)
        if can_supply and immortal and sponsor.unit.capabilities.resource_tier>=2 and sponsor.current>=c.sponsored_attack_cost>0:
            return (2,'energy',c.sponsored_attack_cost)
        if own:return (1,'self',c.operating_cost)
        if can_supply:
            mana=sponsor.current if sponsor.unit.capabilities.resource_link=='legacy_mp' else sponsor.mana_current
            if mana>=c.sponsored_mp_cost>0:return (1,'mp',c.sponsored_mp_cost)
        return (0,'none',0.)

    def pay_operating_attack(self,state):
        tier,source,cost=self.operating_attack(state)
        if not tier:return 0
        if source=='self':
            state.operating_energy-=cost
            text=f'{state.unit.name}使用自身能源发动{"仙阶" if tier==2 else "凡阶"}攻击，耐久 -{cost:g}，剩余{state.operating_energy:g}。'
        else:
            sponsor=self.units[state.unit.capabilities.attack_resource_owner]
            if source=='energy' or sponsor.unit.capabilities.resource_link=='legacy_mp':
                self._energy(sponsor.unit.id,sponsor.current-cost)
            else:sponsor.mana_current-=cost
            if source=='mp':sponsor.supply_mp_spent+=cost
            text=f'{state.unit.name}能源不足以支撑本次{"仙阶" if tier==2 else "凡阶"}攻击，由{sponsor.unit.name}垫付{cost:g}{"元力" if source=="energy" else "MP"}，不消耗能源耐久。'
        self.frame.events.append(text)
        return tier
