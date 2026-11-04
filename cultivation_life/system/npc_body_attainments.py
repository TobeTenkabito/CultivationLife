"""Training belongs to the original physical body, including a possessed host."""
from .combat.actor_state import read


from ..npc_body_schema import validate


def rank(owner,family,key,level):
    # Keep the original innate growth floor; teaching never weakens another art.
    ranks=validate(read(owner,'body_attainments',{}) or {}).get(family,{})
    return max(min(10,max(0,level)//5),ranks.get(key,0))
