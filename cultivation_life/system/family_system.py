"""Base-game descendants, family decisions and authoritative family finance."""
from __future__ import annotations

from ..npc_custody import is_free
from ..relationship_records import find_person

import copy
import math
from dataclasses import fields

from ..content_registry import ITEM_CATALOG, REALMS, ROOT_DEFINITIONS, WORLD_SYSTEMS
from ..models import HistoryRecord, SectNpc
from ..rules import add_item, combat_power, remove_item
from ..runtime import decode_rng, encode_rng, now_iso
from ..world_state import race_pair, RELATION_LABELS
from .crafting_system import remove_crafted_artifact
from .faction_geography import can_enter_faction, require_faction_admission
from .economy import organizations as finance


class FamilySystemMixin:
    @staticmethod
    def _family_equipment(player, item):
        if item.quantity <= 0 or not set(item.tags) & {'equipment', 'artifact'}:
            return None
        if item.crafted_artifact_id:
            artifact = next((a for a in player.crafted_artifacts if a['id'] == item.crafted_artifact_id), None)
            if not artifact or artifact.get('is_natal') or artifact.get('tianji'):
                return None
            power = float(artifact.get('actual_stats', {}).get('combat_power', 0))
        else:
            power, artifact = float(item.combat_bonus), None
        return (power, artifact) if power > 0 else None

    @staticmethod
    def _family_world_tier(world):
        return int(WORLD_SYSTEMS['world_profiles'].get(world, {}).get('tier', 1))

    @staticmethod
    def _family_child_npc(child):
        data = {f.name:copy.deepcopy(child[f.name]) for f in fields(SectNpc) if f.name in child}
        data.update(title='嫡系后人', realm_index=int(child.get('realm_index', 0)),
                    layer=int(child.get('layer', 1)), age=int(child.get('age', 0)), lifespan=child.get('lifespan'))
        return SectNpc(**data)

    def _family_register_children(self, game):
        family = game.family
        if not family or family.extinct:
            return
        family.kind = 'family'
        known = {n.id for n in family.npcs}
        for child in game.player.offspring:
            if (is_free(child) and child.get('cultivation_started')
                    and child.get('world') == family.world and child['id'] not in known
                    and not child.get('family_traits', {}).get('expelled') and can_enter_faction(family, child)):
                member = self._family_child_npc(child)
                member.family_traits['kin'] = True
                family.npcs.append(member)
                known.add(member.id)

    def _family_is_kin(self, game, npc):
        return bool(npc.family_traits.get('kin') or any(c.get('id') == npc.id for c in game.player.offspring))

    def _family_relation(self, game, other):
        if not game.family:
            return {'status':'neutral', 'affinity':0}
        return game.sect_relations.setdefault(race_pair(game.family.id, other.id),
            {'status':'neutral', 'affinity':0, 'since_age':game.player.age})

    def _family_total_power(self, game, family):
        members = family.npcs if family is game.family else self._sect_members(game, family)
        total = sum(self._npc_power(n) for n in members if n.alive and n.world == family.world)
        if (family is game.family or game.player.faction_id == family.id) and game.player.alive and game.player.world == family.world:
            total += combat_power(game.player)
        return round(total, 1)

    def _family_elites(self, game, entity):
        threshold = 2 + self._family_world_tier(entity.world)
        members = entity.npcs if entity is game.family else self._sect_members(game, entity)
        ranks = [(n.realm_index, n.layer) for n in members if n.alive and n.world == entity.world and n.realm_index >= threshold]
        if (entity is game.family or game.player.faction_id == entity.id) and game.player.world == entity.world:
            rank = self._actual_player_realm(game.player)
            if rank[0] >= threshold:
                ranks.append(rank)
        return ranks

    def _family_infusion(self, game, npc):
        tier = self._family_world_tier(npc.world)
        heavenly = ROOT_DEFINITIONS.get(npc.spirit_root, {}).get('tier') == '天灵根'
        cap = 1 + tier + int(heavenly)
        rank = (npc.realm_index, npc.layer)
        target = (npc.realm_index, npc.layer + 1) if npc.layer < REALMS[npc.realm_index].layers else (npc.realm_index + 1, 1)
        cost = max(30, int((npc.realm_index + 1) ** 3 * 25 * (1 + npc.layer / 3)))
        allowed = (is_free(npc) and npc.age >= 16 and npc.spirit_root != 'none' and npc.world == game.player.world
                   and rank < self._actual_player_realm(game.player) and target <= (cap, REALMS[cap].layers)
                   and game.player.opportunity >= cost)
        return {'cap_realm':cap, 'cap_name':f'{REALMS[cap].name}后期', 'cost':cost, 'allowed':bool(allowed), 'target':target}

    def _family_decision_member(self, game, npc, sect):
        if not npc.alive or npc.world != sect.world or npc.faction_id != sect.id or sect.extinct:
            return False
        if self._intrigue_enabled():
            return self._intrigue_has_decision_authority(game, 'sect', sect.id, npc.id)
        return npc.realm_index >= self._governance_threshold(sect.world)

    def _family_assign_office(self, game, npc, sect):
        if not self._intrigue_enabled():
            return
        record = self._ensure_intrigue_faction(game, 'sect', sect.id)
        specs = self._intrigue_position_specs('sect')
        for key, spec in specs.items():
            if key in {'leader','guest_elder'} or npc.realm_index < max(self._intrigue_decision_threshold('sect'),int(spec.get('minimum_realm', 99))):
                continue
            old = self._find_npc(game, str(record.get('positions', {}).get(key) or ''))
            if not old or (npc.realm_index, npc.layer) > (old.realm_index, old.layer):
                record['positions'][key] = npc.id
                return

    def _family_log(self, game, action, text, changes=None):
        game.history.append(HistoryRecord('SYS_FAMILY_' + action.upper(), 1, game.player.age,
            '家族事务', action, action, text, changes or {}, ['system','family',f'world:{game.family.world if game.family else game.player.world}']))

    def family_action(self, game_id, action, payload):
        self.assert_guixu_operation_allowed(game_id, 'family-action')
        game = self._load(game_id)
        player, family = game.player, game.family
        if not player.alive or game.pending_event or player.imprisonment:
            raise ValueError('当前状态无法处理家族事务')
        self._family_register_children(game)
        rng = decode_rng(game.seed, game.rng_state)
        child = next((c for c in player.offspring if c.get('id') == payload.get('npc_id')), None)
        authority = find_person(game, str(payload.get('npc_id', '')))
        if authority and authority.roster_state != 'active':
            raise ValueError('受控或离册人物不能参与家族事务')
        npc = next((n for n in family.npcs if n.id == payload.get('npc_id')), None) if family and not family.extinct else None
        if not npc and child:
            npc = self._family_child_npc(child)
        personal = action in {'teach', 'gift_equipment', 'invite', 'infuse'}
        if personal:
            if not child and not (npc and self._family_is_kin(game, npc)):
                raise ValueError('只能与有灵根的家族后代互动')
            if not npc or not npc.alive or npc.age < 16 or npc.spirit_root == 'none' or npc.world != player.world:
                raise ValueError('后代须已满16岁、拥有灵根、仍在世并与你同界')
        elif not family or family.extinct or family.world != player.world or not (family.founded_by_player or self._has_family_voice(game)):
            raise ValueError('须身在家族所在界面，并拥有家族决策权')

        if action == 'teach':
            technique = next((t for t in player.known_techniques if t.id == payload.get('technique_id')), None)
            if not technique:
                raise ValueError('只能传授自己已掌握的功法')
            learned = npc.family_traits.setdefault('techniques', {})
            bonus = max(0.0, float(technique.combat_bonus))
            previous = float(learned.get(technique.id, 0))
            if bonus <= previous:
                raise ValueError('该功法的当前威能已传授，不能重复叠加')
            npc.family_combat_bonus += bonus - previous
            learned[technique.id] = bonus
            summary = f'你向{npc.name}传授{technique.name}，战力增加{bonus - previous:,.0f}。'
        elif action == 'gift_equipment':
            item = next((i for i in player.inventory if i.id == payload.get('item_id') and i.quantity > 0), None)
            equipment = self._family_equipment(player, item) if item else None
            if not equipment:
                raise ValueError('请选择行囊中可转移的装备；本命法宝及天机神兵不能直接赠与')
            if game.natal_artifact and item.id == game.natal_artifact.get('item_id'):
                raise ValueError('本命法宝不能赠与')
            bonus, artifact = equipment
            if artifact:
                remove_crafted_artifact(player, artifact)
            else:
                remove_item(player, item.id)
            npc.family_traits.setdefault('equipment', []).append({'id':item.id,'name':item.name,'power':bonus,
                                                                  'artifact':copy.deepcopy(artifact)})
            npc.family_combat_bonus += bonus
            summary = f'你赠予{npc.name}{item.name}，其战力增加{bonus:,.0f}。'
        elif action == 'invite':
            if any(m.get('id') == npc.id for m in player.party):
                raise ValueError('该后代已在同行队伍中')
            if len(player.party) >= int(WORLD_SYSTEMS['party']['max_companions']):
                raise ValueError('同行队伍已满')
            player.party.append({'id':npc.id})
            summary = f'{npc.name}加入你的同行队伍。'
        elif action == 'infuse':
            infusion = self._family_infusion(game, npc)
            if not infusion['allowed']:
                raise ValueError(f"灌顶须修为严格高于后代、机缘不少于{infusion['cost']}，上限为{infusion['cap_name']}")
            player.opportunity -= infusion['cost']
            npc.realm_index, npc.layer = infusion['target']
            npc.cultivation_progress = 0
            npc.lifespan = max(npc.lifespan or 0, npc.age + 1, int(REALMS[npc.realm_index].lifespan[0]))
            summary = f'你消耗{infusion["cost"]}机缘，为{npc.name}灌顶至{self._npc_realm_name(npc)}。'
        elif action == 'reproduction':
            if not isinstance(payload.get('enabled'), bool):
                raise ValueError('请选择开启或停止繁衍')
            game.family_state['reproduction_enabled'] = payload['enabled']
            summary = '族内恢复婚配育嗣。' if payload['enabled'] else '家族发布止育决议，已婚族人暂停繁衍。'
        elif action == 'marry':
            if not npc or not npc.alive or npc.age < 16 or not self._family_is_kin(game, npc) or npc.family_traits.get('spouse_id'):
                raise ValueError('须选择适婚、未婚且非外门的族人')
            partner_id = str(payload.get('partner_id') or '')
            partner = next((n for n in family.npcs if n.id == partner_id), None)
            if partner_id:
                def parents(member):
                    ids = member.family_traits.get('parents')
                    return set(ids) if ids else ({'player', 'companion'} if any(c['id']==member.id for c in player.offspring) else set())
                if (not partner or not partner.alive or partner.age < 16 or not self._family_is_kin(game, partner)
                        or partner.id == npc.id or partner.gender == npc.gender or partner.family_traits.get('spouse_id')
                        or parents(partner) & parents(npc) or partner.id in parents(npc) or npc.id in parents(partner)):
                    raise ValueError('婚配对象须为未婚适龄族人，不能安排同胞近亲婚配')
            else:
                cost = 150 * self._family_world_tier(family.world)
                if not remove_item(player, 'spirit_stone', cost):
                    raise ValueError(f'外聘婚配需支付{cost}灵石礼仪费用')
                serial = int(game.family_state.get('marriage_serial', 0)) + 1
                game.family_state['marriage_serial'] = serial
                rank = max(1, npc.realm_index)
                partner = SectNpc(f'{family.id}_spouse_{serial}', rng.choice(['沈清','陆瑶','顾宁','楚安'])+str(serial),
                    '姻亲族人', rank, 1, max(18, min(npc.age, 40)), max(110, int(REALMS[rank].lifespan[0])) if REALMS[rank].lifespan else None,
                    spirit_root=self._random_npc_root(rank, rng), world=family.world, path=family.path,
                    gender='female' if npc.gender == 'male' else 'male', affinity=50, family_traits={'kin':True})
                require_faction_admission(family, partner)
                from .combat.npc_lifecycle import initialize_native
                initialize_native(partner, WORLD_SYSTEMS.get("transcendent_combat", {}), now=player.age)
                family.npcs.append(partner)
            npc.family_traits['spouse_id'] = partner.id
            partner.family_traits['spouse_id'] = npc.id
            summary = f'家族为{npc.name}与{partner.name}安排婚姻；是否育嗣仍按双方较高境界的自然概率结算。'
        elif action == 'send_sect':
            sect = game.sects.get(str(payload.get('sect_id', '')))
            if not npc or not npc.alive or npc.age < 16 or not sect or sect.kind != 'sect' or sect.extinct or sect.world != family.world:
                raise ValueError('须选择成年族人与同界宗门')
            if self._family_relation(game, sect)['status'] not in {'alliance','vassal'}:
                raise ValueError('家族须与目标宗门结盟或确立依附关系')
            if npc.faction_id:
                raise ValueError('该族人已经在宗门任职')
            require_faction_admission(sect, npc)
            npc.faction_id = sect.id
            self._family_assign_office(game, npc, sect)
            summary = f'{npc.name}进入{sect.name}，保留族籍。' + ('凭修为获得议事权。' if self._family_decision_member(game,npc,sect) else '从门下历练起步。')
        elif action == 'diplomacy':
            other = game.sects.get(str(payload.get('target_id', '')))
            status = str(payload.get('status', ''))
            if not other or other.extinct or other.world != family.world or status not in {'alliance','neutral','vassal','war'}:
                raise ValueError('请选择同界存续势力及有效外交决策')
            relation = self._family_relation(game, other)
            if relation['status'] == 'war':
                raise ValueError('双方正在交战，须先在战争界面议和')
            cooldown = f'diplomacy:{other.id}'
            if game.family_state.get(cooldown) == player.age:
                raise ValueError('本年度已向该势力交涉')
            game.family_state[cooldown] = player.age
            if status == 'vassal':
                own_elites, their_elites = len(self._family_elites(game, family)), len(self._family_elites(game, other))
                dominant = family if (own_elites, self._family_total_power(game,family)) > (their_elites,self._family_total_power(game,other)) else other
                relation.update(overlord=dominant.id, subject=other.id if dominant is family else family.id)
            else:
                relation.pop('overlord', None); relation.pop('subject', None); relation.pop('vassal', None)
            relation.update(status=status, since_age=player.age)
            if status == 'war':
                self._start_war(game,'sect',family.id,other.id,initiated_by_player=True)
            summary = f'{family.name}与{other.name}{RELATION_LABELS.get(status,status)}。'
        elif action in {'fund','gather','expel'}:
            if action == 'expel' and not self._intrigue_enabled():
                raise ValueError('家族内政需要启用合纵连横 DLC')
            fiscal = finance.register(game, 'family', family.id, family.world)
            treasury = finance.key('family', family.id)
            if action == 'fund':
                amount = payload.get('amount')
                if isinstance(amount,bool) or not isinstance(amount,int) or amount <= 0:
                    raise ValueError('注资须为正整数灵石')
                finance.transfer_value(game, 'player', treasury, amount, '玩家家族注资')
                debt = int(game.family_state.get('debt',0))
                paid = min(debt,amount)
                finance.procure(game, treasury, family.world, paid, '偿还家族供养欠款')
                game.family_state['debt'] = debt-paid
                summary = f'你向家族资材注入{amount}灵石。'
            elif action == 'gather':
                if game.family_state.get('gather_age') == player.age:
                    raise ValueError('本年已组织过产业经营')
                game.family_state['gather_age'] = player.age
                amount = finance.produce(game, self.maps, family, fiscal, extra=True)
                fiscal['income'] += amount
                summary = f'家族组织经营采集，本地市场实际收购所得{amount}灵石。'
            else:
                if not npc or npc not in family.npcs:
                    raise ValueError('该修士不在族籍')
                npc.family_traits['expelled'] = True
                family.npcs.remove(npc)
                if not child:
                    game.notable_npcs[npc.id] = npc
                player.party[:] = [m for m in player.party if m.get('id') != npc.id]
                summary = f'{npc.name}被移出族籍，不再领取家族供养。'
        else:
            raise ValueError('未知家族操作')
        if child and npc:
            child.update(npc.to_dict())
            child['cultivation_started'] = npc.realm_index > 0
        self._family_log(game, action, summary)
        game.rng_state = encode_rng(rng); game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _family_annual_governance(self, game, rng):
        family = game.family
        if not family or family.extinct:
            return []
        state = game.family_state
        if state.get('settled_age') == game.player.age:
            return []
        state['settled_age'] = game.player.age
        news = []
        people = [n for n in family.npcs if n.alive and n.world == family.world]
        by_id = {n.id:n for n in people}
        if state.get('reproduction_enabled', True):
            for parent in people:
                spouse = by_id.get(parent.family_traits.get('spouse_id'))
                if not spouse or parent.id >= spouse.id or min(parent.age,spouse.age) < 16:
                    continue
                chance = float(WORLD_SYSTEMS['family']['conception_chance_by_realm'].get(str(max(parent.realm_index,spouse.realm_index)),0))
                if chance <= 0 or rng.random() >= chance:
                    continue
                roots = [r for r in (parent.spirit_root,spouse.spirit_root) if r in ROOT_DEFINITIONS and r != 'none']
                root = rng.choice(roots or ['supreme_wood'])
                serial = int(state.get('birth_serial',0))+1;state['birth_serial']=serial
                child = {'id':f'{family.id}_born_{serial}', 'name':family.name[:1]+rng.choice(['宁','安','澄','清'])+str(serial),
                    'age':0,'alive':True,'world':family.world,'spirit_root':root,'cultivation_started':False,
                    'realm_index':0,'layer':1,'path':family.path,'race':parent.race,'lifespan':rng.randint(80,100),
                    'gender':rng.choice(['male','female']),'parents':[parent.name,spouse.name],
                    'family_traits':{'kin':True,'parents':[parent.id,spouse.id]}}
                game.player.offspring.append(child)
                self._family_log(game,'birth',f'{parent.name}与{spouse.name}诞下{child["name"]}，天生具有{self._npc_root_name(root)}。')
        threshold = 2 + self._family_world_tier(family.world)
        if not self._family_elites(game,family):
            family.pressure += 1
            text = f'{family.name}缺少{REALMS[threshold].name}修士坐镇，周边势力排挤加重（{family.pressure}/3）。'
            self._family_log(game,'pressure',text)
            if family.world == game.player.world:news.append(text)
            if family.pressure >= 3:
                self._family_dissolve(game,'连续三年无人达到立族修为底线')
                return news
        else:
            family.pressure = 0
        tribute, office_income = 0, 0
        for sect in game.sects.values():
            if sect.extinct or sect.world != family.world or sect.kind == 'family':continue
            relation = self._family_relation(game,sect)
            officials = [n for n in people if self._family_decision_member(game,n,sect)]
            key = f'annex_pressure:{sect.id}'
            if relation['status'] == 'vassal' and relation.get('overlord') == sect.id:
                if not officials and len(self._family_elites(game,family)) < len(self._family_elites(game,sect)):
                    state[key] = int(state.get(key,0))+1
                    self._family_log(game,'annex_warning',f'{sect.name}要求合并附属家族，族内无人拥有宗门决策权（{state[key]}/3）。')
                    if state[key] >= 3:
                        self._family_dissolve(game,f'被依附宗门{sect.name}并入',sect)
                        return news
                else:state[key]=0
            else:state[key]=0
            if sect.kind == 'institution':
                continue
            finance.register(game, 'sect', sect.id, sect.world)
            finance.register(game, 'family', family.id, family.world)
            source, target = finance.key('sect', sect.id), finance.key('family', family.id)
            if state.get('finance_year', -1) < game.player.age:
                if officials and relation['status'] != 'war' and family.world == game.player.world and game.player.alive:
                    office_income += finance.pay(game, source, 'player', int(sum(max(100,n.realm_index**4*12) for n in officials)), '宗门族人奉赠')
                if relation['status'] == 'vassal' and relation.get('overlord') == family.id:
                    tribute += finance.pay(game, source, target, max(200,int(self._family_total_power(game,sect)**.5 * 8)), '附属宗门上供')
        fiscal = finance.register(game, 'family', family.id, family.world)
        if state.get('finance_year', -1) >= game.player.age:
            return news
        state['finance_year'] = game.player.age
        income, expenses = fiscal['income'] + tribute, fiscal['expense']
        surplus = max(0, income - expenses)
        dividend = 0
        if family.world == game.player.world and game.player.alive and not state.get('debt', 0):
            dividend = finance.pay(game, finance.key('family', family.id), 'player', int(surplus * .15), '家族年度盈余分红')
        fiscal['benefit_due'], fiscal['benefit_paid'] = int(surplus * .15), dividend
        fiscal['expense'] += dividend
        state['ledger'] = dict(year=game.player.age, income=income, expenses=expenses, balance=income-expenses,
            tribute=tribute, dividend=dividend, office_income=office_income, shortfall=int(state.get('debt', 0)))
        if dividend or office_income:
            self._family_log(game,'dividend',f'家族盈余分红{dividend}灵石，宗门族人奉赠{office_income}灵石；只在本界发放。')
        if state.get('debt', 0):
            state['deficit_years'] = int(state.get('deficit_years',0))+1
            self._family_log(game,'deficit',f'家族供养欠款{state["debt"]}灵石，请注资、经营或调整族籍。')
            if state['deficit_years'] >= 2:
                outsider = next((n for n in people if not self._family_is_kin(game,n)),None)
                if outsider:
                    family.npcs.remove(outsider)
                    game.notable_npcs[outsider.id] = outsider
                    self._family_log(game,'desertion',f'连年拖欠供养，外姓门人{outsider.name}离族。')
        else:
            state['deficit_years']=0
        return news

    def _family_dissolve(self, game, reason, absorber=None):
        family = game.family
        family.extinct = True
        for npc in family.npcs:
            child = next((c for c in game.player.offspring if c.get('id')==npc.id),None)
            if absorber and npc.alive and can_enter_faction(absorber, npc):
                npc.faction_id = absorber.id
                if not any(n.id==npc.id for n in absorber.npcs):absorber.npcs.append(npc)
            elif not child and npc.alive:
                game.notable_npcs[npc.id] = npc
            if child:child.update(npc.to_dict())
        self._family_log(game,'dissolved',f'{family.name}{reason}，独立族籍解散，存活族人并未被判定死亡。')

    def _family_presentation(self, game, result):
        family = game.family
        result.update(reproduction_enabled=game.family_state.get('reproduction_enabled',True),
            gather_used=game.family_state.get('gather_age') == game.player.age,
            intrigue_enabled=self._intrigue_enabled(),pressure=family.pressure if family else 0,
            protection_realm=REALMS[2+self._family_world_tier(family.world if family else game.player.world)].name,
            total_power=self._family_total_power(game,family) if family and not family.extinct else 0)
        result['can_manage'] = bool(family and not family.extinct and family.world==game.player.world and (family.founded_by_player or self._has_family_voice(game)))
        result['can_found'] = bool((not family or family.extinct) and any(is_free(c) and c.get('cultivation_started') and c.get('world')==game.player.world for c in game.player.offspring))
        known_techniques = [t for t in game.player.known_techniques if t.combat_bonus>0]
        result['teaching_options'] = [{'id':t.id,'name':t.name,'power':t.combat_bonus} for t in known_techniques]
        result['equipment_options'] = [{'id':i.id,'name':i.name,'power':equipment[0],'quantity':i.quantity} for i in game.player.inventory
            if (equipment := self._family_equipment(game.player,i))
            and not (game.natal_artifact and i.id == game.natal_artifact.get('item_id'))]
        for row in [*result.get('offspring',[]),*result.get('roster',[])]:
            npc = self._find_npc(game,str(row.get('id')))
            if not npc:continue
            row['can_interact'] = bool(is_free(npc) and npc.age>=16 and npc.spirit_root!='none' and npc.world==game.player.world
                                       and (self._family_is_kin(game,npc) or row in result.get('offspring',[])))
            row['combat_power'] = self._npc_power(npc) if npc.alive else 0
            row['infusion'] = self._family_infusion(game,npc)
            row['spouse_name'] = next((n.name for n in family.npcs if n.id==npc.family_traits.get('spouse_id')),None) if family else None
            row['can_marry'] = bool(is_free(npc) and npc.age>=16 and self._family_is_kin(game,npc) and not npc.family_traits.get('spouse_id'))
            row['member_type'] = '本家' if self._family_is_kin(game,npc) else '外姓门人'
            row['sect_name'] = game.sects[npc.faction_id].name if npc.faction_id in game.sects else None
            row['in_party'] = any(m.get('id')==npc.id for m in game.player.party)
        powers = [s for s in game.sects.values() if not s.extinct and s.world==game.player.world]
        result['other_families'] = [{'id':s.id,'name':s.name,'total_power':self._family_total_power(game,s),
            'living_count':sum(n.alive for n in s.npcs),'description':s.description} for s in powers if s.kind=='family']
        result['diplomacy'] = [{'id':s.id,'name':s.name,'kind':s.kind,'total_power':self._family_total_power(game,s),
            **copy.deepcopy(self._family_relation(game,s))} for s in powers] if family and not family.extinct and family.world==game.player.world else []
        result['ledger'] = None
        if family and not family.extinct and family.world==game.player.world:
            record=game.intrigue_state.get('factions', {}).get(f'family:{family.id}', {})
            result['ledger'] = {**copy.deepcopy(game.family_state.get('ledger',{})), 'resources':int(record.get('resources',0)), 'shortfall':int(game.family_state.get('debt',0))}
            result['finance'] = finance.public_finance(game, 'family', family.id)
        return result
