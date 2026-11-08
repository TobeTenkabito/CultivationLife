"""One original same-world road quote for officers and rescued people."""
def route(maps,game,npc,origin,dest):
    if origin==dest:
        maps.location('celestial',origin)
        return dict(origin=origin,destination=dest,route=[origin],years=0,progress=0)
    plan=maps.travel_plan('celestial',origin,dest,npc.realm_index)
    if plan.status!='ok':raise ValueError('属员或伤者的原道路与境界门槛不允许通行')
    from .earth_dispute_roads import delay
    return dict(origin=origin,destination=dest,route=list(plan.route),years=plan.years+delay(game,plan.route),progress=0)
