"""NPC workbench reads the ordinary projection; writes use registered capabilities."""
from .registry import Command


def inspect(ctx):
    return {'view': ctx.services.preview(ctx.session, 'npc-development', {}),
            'supply_enabled': ctx.document['player'].get('combat_plan', {}).get('puppet_supply', True)}


def register(registry):
    registry.register(Command('npc development inspect', 'preview',
        'Inspect ordinary NPC training targets, portraits, quotes, restrictions, high-tier '
        'voisinage/body options and puppet energy in a disposable copy. Does not save or consume RNG.',
        inspect))
