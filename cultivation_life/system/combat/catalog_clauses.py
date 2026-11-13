"""Named-clause gates over observed receipts, never hidden opponent builds."""


def admits(runtime, owner, book, record, fact):
    effect = book['effect']; flags = set(effect['clauses'])
    state = runtime.battle.units[owner]
    known = runtime.facts[owner]
    observed = known.get('cast') or {}
    checks = {
        'source_repeat': observed.get('count',0) >= 2,
        'source_changed': observed.get('changed',False),
        'two_sources': known.get('source_kinds',0) >= 2,
        'second_source': known.get('source_kinds',0) >= 2 and observed.get('ordinal') == 2,
        'source_hits_only': observed.get('actual',False),
        'source_hurt_owner': observed.get('actual',False) and observed.get('target')==owner and known.get('hurt_source')==observed.get('source'),
        'source_current': observed.get('round') == runtime.round,
        'paid_source': observed.get('paid',False),
        'incoming_last': known.get('hurt_round') == runtime.round-1 or fact.get('kind') == 'incoming',
        'outgoing_required': known.get('hit_round',0) > 0,
        'both_directions': known.get('hit_seq',0) > record['consumed'] and known.get('hurt_seq',0) > record['consumed'],
        'reverse_to_first': known.get('changed') and known.get('first') is True,
        'reverse_to_second': known.get('changed') and known.get('first') is False,
        'reverse_either': known.get('changed',False),
        'had_second': known.get('ever_second',False),
        'formation_required': runtime.battle._semantic_environment.get('environment.formation',False),
        'domain_paid': known.get('field_paid_round') == runtime.round,
        'domain_ended': known.get('field_ended_round') == runtime.round,
        'shield_used': known.get('shield_used_seq',0) > record['consumed'],
        'attacked_shield': known.get('attacked_shield_seq',0) > record['consumed'],
        'body_required': state.body > 0 and not state.unit.capabilities.technique_context.get('bodiless',False),
        'form_required': bool(state.unit.capabilities.technique_context.get('form')),
        'target_defended': bool(known.get('hit_round')),
        'forecast_last': observed.get('round',0) >= runtime.round-1 and observed.get('actual',False),
        'first_form_only': record['used'] == 0,
    }
    if any(flag in checks and not checks[flag] for flag in flags):
        return False
    if 'two_sources_memory' in flags:
        sources=[]
        import json
        for key,row in sorted(runtime.observations[owner].items(),key=lambda pair:pair[1]['ordinal']):
            source=json.loads(key)[0]
            if source not in sources:sources.append(source)
        if observed.get('source') not in sources[:2]:return False
    if 'first_target' in flags and known.get('first_target') != fact.get('target'):
        return False
    if effect['category'] == 'body' and not checks['body_required']:
        return False
    if effect['category'] == 'transformation' and not checks['form_required']:
        return False
    if effect['category'] == 'divine_sense' and runtime.battle._semantic_environment.get('environment.forbidden_sense'):
        return False
    return True


def choose(runtime, owner, book, record):
    """Deterministic, nonclairvoyant policy shared by player and NPC automation."""
    s = runtime.battle.units[owner]
    e = book['effect']; payload = e['payload']
    if payload == 'five_step_rotation':
        return ('breach','recover','shield','strike','mobility')[record['rotation'] % 5]
    if payload == 'alternating_choice':
        offset = int('restore_first' in e['clauses'])
        if 'reset_after_cycle' in e['clauses'] and record['completed']>=2 and not record['reset']:
            record['reset']=True
            record['rotation']=(int(s.vitality<runtime.initial_state[owner]*.75)-offset)%2
        return ('strike','recover')[(record['rotation'] + offset) % 2]
    if payload == 'initiative_choice':
        return 'breach' if runtime.facts[owner].get('first',True) else 'guard'
    if payload == 'four_way_choice':
        if runtime.debuff(owner): return 'cleanse'
        if s.vitality>=runtime.initial_state[owner]*.5 and runtime.facts[owner].get('first') is False:return 'mobility'
        return 'guard' if s.vitality < runtime.initial_state[owner] * .5 else 'breach'
    if payload == 'offense_restore_choice':
        return 'recover' if s.vitality < runtime.initial_state[owner] * .75 else 'strike'
    if payload == 'forecast_choice':
        return 'recover' if s.vitality < runtime.initial_state[owner] * .5 else 'shield' if s.vitality < .75 else 'strike'
    if payload == 'cancel_afterburn_for_shield':
        return 'shield' if s.vitality < runtime.initial_state[owner] * .5 else 'strike'
    if e['delivery'] == 'convert_before_payment' and s.vitality < runtime.initial_state[owner] * .4:
        return 'shield'
    return ''
