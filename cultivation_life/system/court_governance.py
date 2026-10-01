"""One bounded cabinet agenda per court unit; shares player policy settlement."""
from ..models import HistoryRecord


from .court_lifecycle import CourtLifecycleMixin


class CourtGovernanceMixin(CourtLifecycleMixin):
    def _court_retire_unavailable(self, game):
        court = game.heavenly_court
        for office_id, holder in court['offices'].items():
            if not holder:
                continue
            key = holder['holder_id']
            official = court['officials'].get(key)
            expired = holder.get('end_unit', court['unit']) <= court['unit']
            missing = official is None
            if official and official.get('source') == 'npc':
                npc = self._find_npc(game, key)
                missing = not npc or not npc.alive or npc.world != 'celestial'
                if missing:
                    court['officials'].pop(key, None)
            if expired or missing:
                court['offices'][office_id] = None

    def _court_autonomous_votes(self, court, actor_id, law_id, desired, rng):
        agenda = self._court_config()['autonomous_governance']['agenda']
        yes = abstain = 0
        for office_id, holder in court['offices'].items():
            if not holder:
                continue
            key = holder['holder_id']
            if key == 'player':
                # Autonomous deliberation never spends the player's influence,
                # casts their vote, changes their support or honors their pledge.
                abstain += 1
                continue
            preferred = agenda[office_id]['laws'].get(law_id)
            probability = .5 if preferred is None else .8 if preferred == desired else .2
            yes += key == actor_id or rng.random() < probability
        return yes, abstain

    def _court_govern(self, game, rng):
        court = game.heavenly_court
        unit = int(court['unit'])
        if court.get('open_election') or court.get('governed_unit', -1) >= unit:
            return []
        self._court_retire_unavailable(game)
        chairs = [(key, h) for key, h in court['offices'].items() if h and h['holder_id'] != 'player']
        court['governed_unit'] = unit
        if not chairs:
            return []
        # At most seven entries, no population scan or per-year political tick.
        office_id, holder = chairs[(max(1, unit)-1) % len(chairs)]
        actor_id = holder['holder_id']
        cfg = self._court_config()['autonomous_governance']
        agenda = cfg['agenda'][office_id]
        messages = []

        def record(kind, result, summary):
            text = f"{holder['holder_name']}主持天庭议政：{summary}"
            row = dict(unit=unit, actor_id=actor_id, name=holder['holder_name'], kind=kind, result=result, summary=text)
            court.setdefault('governance_log', []).append(row)
            court['governance_log'] = court['governance_log'][-24:]
            game.history.append(HistoryRecord('SYS_COURT_GOVERNANCE',1,game.player.age,'七曜议政',actor_id,result,text,{'unit':unit},['celestial','heavenly_court','politics']))
            messages.append(text)

        candidates = [(key, desired) for key, desired in agenda['laws'].items()
                      if bool(court['laws'].get(key)) != desired
                      and unit-court.get('law_attempted_at',{}).get(key,-1000) >= cfg['law_cooldown_units']
                      and unit-court.get('law_changed_at',{}).get(key,-1000) >= cfg['law_cooldown_units']]
        if candidates and court['treasury'] >= self._court_config()['policy_treasury_cost']:
            law_id, desired = candidates[(unit-1) % len(candidates)]
            if desired:
                conflict = next((key for key in self._court_conflicts(law_id) if court['laws'].get(key)), None)
                if conflict:
                    law_id, desired = conflict, False
            court.setdefault('law_attempted_at',{})[law_id] = unit
            result, summary = self._court_vote_law(game,law_id,desired,rng,actor_id=actor_id)
            record('law', result, summary)

        active = {row['id'] for row in court['active_decrees']}
        # Policy effects, costs, prerequisites and slots all use the same service
        # as player actions; rejected candidates do not mutate the treasury.
        choices = list(agenda['decrees'])
        if court['treasury'] < 500:
            choices = ['levy', *choices]
        for decree_id in dict.fromkeys(choices):
            if decree_id in active:
                continue
            target = ''
            if decree_id == 'direct_appointment':
                eligible = [o['id'] for o in court['officials'].values() if o.get('source')=='npc' and o.get('grade',0)>=9]
                if not eligible:
                    continue
                target = rng.choice(eligible)
            try:
                result, summary = self._court_enact_decree(game,decree_id,target,rng,actor_id=actor_id)
            except ValueError:
                continue
            record('decree',result,summary)
            break
        return messages
