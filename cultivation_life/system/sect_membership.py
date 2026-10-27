"""Release the original member from offices and roster, without killing or cloning."""
def release(game, entity, record, npc):
    for key, holder in list(record.get('positions',{}).items()):
        if holder==npc.id:
            record['positions'][key]=None
    if record.get('controller_id')==npc.id:
        record['controller_id']=None
    record['guests']=[r for r in record.get('guests',[]) if r.get('npc_id')!=npc.id]
    from ..npc_custody import transfer_free_person
    transfer_free_person(game,npc)
    # Closed commissions retain provenance; leaving cannot create a claim later.
    for task in record.get('task_board',{}).get('tasks',[]):
        if task['status']=='open' and task['issuer']==npc.id:
            task['status']='cancelled'


def recruiting(game, identity):
    root=getattr(game,'_game',game)
    entity=root.sects.get(identity)
    if (not entity or not root.player.alive or root.player.faction_id!=identity
            or root.player.world!=entity.world or game.player.age!=root.player.age):
        return True  # Outside the player's current sect, retain the old recruitment rules.
    return game.intrigue_state.get('factions',{}).get(f'sect:{identity}',{}).get('task_board',{}).get('recruitment_open',True)
