"""Single compare-and-transfer entry for a resolved succession, without rewards."""
def duel_result(report,result,summary):
    """Recognize actual suppression/morale surrender at the nonlethal floor."""
    if result!='stalemate':return result,summary
    updates=report.get('capability_updates',[])
    enemies=[u for u in updates if u.get('side')=='enemy']
    own=next((u for u in updates if u.get('id')=='player'),{})
    rounds=report.get('rounds',[])
    morale=rounds[-1].get('voisinage',{}).get('morale',{}) if rounds else {}
    if own.get('suppressed') or morale.get('player',100)<=0:result='defeat'
    elif enemies and all(u.get('suppressed') or morale.get(u['id'],100)<=0 for u in enemies):result='victory'
    if result!='stalemate':
        report.update(result=result,outcome=result,result_grade='血战胜出' if result=='victory' else '血战落败')
        summary='魔域交锋后，一方被镇压或战意耗尽，王庭裁定认负，停止追击。'
    return result,summary


def exchange(state, rank, *, opponent=None):
    """Original adjacent-title settlement; eligibility belongs to its caller."""
    court,old=state['court'],state['rank']
    holder=opponent if opponent is not None else court['holders'].get(str(rank))
    if opponent is not None and rank:
        previous=next((key for key,value in court['holders'].items() if value==opponent),None)
        if previous and previous not in {str(old),str(rank)}:court['holders'][previous]=court['holders'].get(str(rank))
    if old:court['holders'][str(old)]=holder
    if rank:court['holders'][str(rank)]='player'
    state['rank']=rank;court['protected_until']=state['unit']+8;court['challenge']=None
    if rank==5:state['obligation']=None


def transfer(state, claimant, expected):
    court=state['court'];holders=court['holders']
    if not claimant or claimant==expected or holders.get('5')!=expected:
        raise ValueError('王位持有人已经变化，原战果不能重复用于登位')
    for rank,identity in holders.items():
        if identity==claimant:holders[rank]=None
    holders['5']=claimant
    state['rank']=5 if claimant=='player' else next((int(k) for k,v in holders.items() if v=='player'),0)
    court['offices']={k:v for k,v in court['offices'].items() if v!=claimant}
    court['challenge']=None;court['protected_until']=state['unit']+8
    state['obligation']=None
