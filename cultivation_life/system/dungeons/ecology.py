"""Local expedition ranks and encounter distance, separate from reward quality."""
from ...content_registry import REALMS, WORLD_SYSTEMS

POPULATIONS={'ordinary':(4,3),'rare':(6,4),'epic':(10,6),'legendary':(16,10)}


def floor(world):
    return {1:1,2:6,3:9}[WORLD_SYSTEMS['world_profiles'][world]['tier']]


def stage(realm,layer):
    """Early, middle and late cultivation; layers are subdivisions of these."""
    return min(2,max(0,(layer-1)*3//REALMS[realm].layers))


def site_rank(world,quality,profile,reference,ceiling):
    if quality=='legendary':return ceiling
    if quality=='epic':return min(profile['cap'],profile['realm']+1)
    extra=int(quality=='rare')
    return max(floor(world),min(profile['cap'],profile['realm']+extra,reference[0]+extra))


def person_rank(rng,world,quality,number,reference,realm,profile,ceiling):
    count,near=POPULATIONS[quality]
    # Realm circulation floors constrain treasure, not the cultivation of visitors.
    local=max(1,min(ceiling,reference[0]))
    if quality=='ordinary':
        levels=[i for i in range(1,REALMS[local].layers+1) if abs(stage(local,i)-stage(local,reference[1]))<=2]
        return local,rng.choices(levels,weights=[3 if stage(local,i)==stage(local,reference[1]) else 1 for i in levels])[0]
    if quality=='rare':
        rank=local if number==0 else max(1,min(ceiling,local+rng.choices((-1,0,1),(15,55,30))[0]))
        return rank,max(1,min(REALMS[rank].layers,reference[1]+rng.randint(-2,2)))
    if number<near:
        rank=local if number==0 else max(1,min(ceiling,local+rng.choices((-1,0,1),(15,70,15))[0]))
        layer=max(1,min(REALMS[rank].layers,reference[1]+rng.randint(-2,2)))
    else:
        if number<near+2:
            rank=(local+realm)//2
        else:rank=realm
        rank=max(1,min(ceiling,rank))
        layer=rng.randint(max(1,REALMS[rank].layers-3),REALMS[rank].layers)
    return rank,layer


def appearance_depth(site,role):
    if role['true_realm']>site['ceiling']:return 3
    gap=role['realm']-site['reference'][0]
    return 3 if gap>=3 else 2 if gap>=2 else 0


def close_realms(player_realm,other_realm):
    return abs(player_realm-other_realm)<=1
