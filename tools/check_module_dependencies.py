"""Report explicit Python import cycles and enforce selected architectural boundaries.

Includes function-local imports; excludes TYPE_CHECKING-only imports. Dynamic
imports and Python's implicit package-initializer execution are not modeled.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
from pathlib import Path


# Combat projection consumes shared state/rules, never action or presentation facades.
BATTLE_FACADES = frozenset(f'cultivation_life.system.{name}' for name in (
    'immortal_aperture', 'upper_voisinage', 'upper_institutions', 'asura_court',
))
BATTLE_PROJECTIONS = frozenset(f'cultivation_life.system.{name}' for name in (
    'combat_adapter', 'combat_system', 'combat_plan', 'doctrine.provider', 'spirit_voisinage',
))
BATTLE_SHARED = frozenset(f'cultivation_life.system.{name}' for name in (
    'aperture_resources', 'upper_voisinage_rules', 'doctrine.state', 'institution_state',
))
BATTLE_DEPENDENCY_MODULES = BATTLE_FACADES | BATTLE_PROJECTIONS | BATTLE_SHARED

# Content validation must be usable before the global registry is initialized.
CONTENT_VALIDATORS = frozenset(f'cultivation_life.{name}' for name in (
    'achievement_definitions', 'event_catalog', 'system.map_definition',
    'system.world_transition_schema', 'system.combat.lifecycle_schema',
))
CORE_FACADES = frozenset(f'cultivation_life.{name}' for name in (
    'rules', 'achievements', 'event_repository', 'system.map_system',
    'system.world_transition_system', 'system.combat.npc_lifecycle',
    'system.crafting_system', 'system.ghost_system', 'system.cultivation_policy',
    'system.cultivation_ranks', 'system.monster_identity',
))
CORE_SHARED = frozenset(f'cultivation_life.{name}' for name in (
    'combat_benchmarks', 'cultivation_costs', 'system.crafted_artifact_rules',
    'system.ghost_resources', 'system.npc_cultivation', 'system.cultivation_reserves',
))
MODEL_FOUNDATIONS = frozenset(f'cultivation_life.{name}' for name in (
    'models', 'ancestry', 'cultivation_coordinates', 'system.combat.migration',
))
COURT_FACADES = frozenset(f'cultivation_life.system.{name}' for name in (
    'heavenly_court_system', 'court_governance', 'court_lifecycle', 'yaochi_system',
))


def import_edges(root: Path):
    modules = {}
    for path in (root / 'cultivation_life').rglob('*.py'):
        parts = path.relative_to(root).with_suffix('').parts
        name = '.'.join(parts[:-1] if parts[-1] == '__init__' else parts)
        modules[name] = path
    edges = []
    for name, path in modules.items():
        package = name if path.name == '__init__.py' else name.rpartition('.')[0]

        class Imports(ast.NodeVisitor):
            def visit_If(self, node):
                checking = (isinstance(node.test, ast.Name) and node.test.id == 'TYPE_CHECKING'
                            or isinstance(node.test, ast.Attribute) and node.test.attr == 'TYPE_CHECKING')
                for child in node.orelse if checking else [*node.body, *node.orelse]:
                    self.visit(child)

            def visit_Import(self, node):
                for alias in node.names:
                    add(alias.name, node.lineno)

            def visit_ImportFrom(self, node):
                target = node.module or ''
                if node.level:
                    target = importlib.util.resolve_name('.' * node.level + target, package)
                add(target, node.lineno)
                for alias in node.names:
                    add(f'{target}.{alias.name}', node.lineno)

        def add(target, line):
            if target in modules and target != name:
                edges.append((name, target, line))

        Imports().visit(ast.parse(path.read_text(encoding='utf-8-sig')))
    return modules, sorted(set(edges))


def cycles(modules, edges):
    graph = {name: set() for name in modules}
    for source, target, _line in edges:
        graph[source].add(target)
    indices, low, stack, active, result = {}, {}, [], set(), []

    def visit(name):
        indices[name] = low[name] = len(indices)
        stack.append(name)
        active.add(name)
        for target in sorted(graph[name]):
            if target not in indices:
                visit(target)
                low[name] = min(low[name], low[target])
            elif target in active:
                low[name] = min(low[name], indices[target])
        if low[name] == indices[name]:
            group = []
            while True:
                member = stack.pop()
                active.remove(member)
                group.append(member)
                if member == name:
                    break
            if len(group) > 1:
                result.append(sorted(group))

    for name in sorted(graph):
        if name not in indices:
            visit(name)
    return sorted(result, key=lambda group: (-len(group), group))


def violations(edges):
    invalid = []
    for source, target, line in edges:
        system_to_engine = (source.startswith('cultivation_life.system.')
                            and source != 'cultivation_life.system.asura_system'
                            and (target == 'cultivation_life.engine' or target.startswith('cultivation_life.engine.')))
        domain_to_facade = any(
            source.startswith(f'cultivation_life.system.{area}.')
            and target == f'cultivation_life.system.{area}_system'
            for area in ('economy', 'tianji', 'intrigue', 'crafting', 'formation'))
        domain_to_wiring = any(
            source.startswith(f'cultivation_life.system.{area}.')
            and source != f'cultivation_life.system.{area}.wiring'
            and target == f'cultivation_life.system.{area}.wiring'
            for area in ('economy', 'tianji', 'intrigue', 'crafting', 'formation'))
        shared_definition_cycle = (source, target) in {
            ('cultivation_life.system.economy.exchange', 'cultivation_life.system.exchange_system'),
            ('cultivation_life.system.doctrine.effects', 'cultivation_life.system.doctrine.generation'),
            ('cultivation_life.system.merchant_commission_system', 'cultivation_life.system.merchant_system'),
            ('cultivation_life.monster_bloodline_rules', 'cultivation_life.combat_rule_engine'),
            ('cultivation_life.system.tutorial_walkthrough', 'cultivation_life.system.tutorial_system'),
        }
        shared_to_consumer = (
            source == 'cultivation_life.combat_rule_schema'
            and target in {'cultivation_life.combat_rule_engine', 'cultivation_life.monster_bloodline_rules'}
            or source == 'cultivation_life.system.tutorial_mentorship'
            and target in {'cultivation_life.system.tutorial_system', 'cultivation_life.system.tutorial_walkthrough'})
        battle_reverse_import = (
            source in BATTLE_PROJECTIONS and target in BATTLE_FACADES
            or source in BATTLE_SHARED and target in BATTLE_FACADES | BATTLE_PROJECTIONS
            or (source, target) in {
                ('cultivation_life.system.asura_court', 'cultivation_life.system.upper_institutions'),
                ('cultivation_life.system.spirit_voisinage', 'cultivation_life.system.doctrine.provider'),
            })
        core_reverse_import = (
            source in CONTENT_VALIDATORS
            and target in CORE_FACADES | {'cultivation_life.content_registry'}
            or source in CORE_SHARED and target in CORE_FACADES
            or source == 'cultivation_life.content_registry' and target in CORE_FACADES
            or source in MODEL_FOUNDATIONS
            and (target.startswith('cultivation_life.system.') and target not in MODEL_FOUNDATIONS
                 or target in {'cultivation_life.content_registry', 'cultivation_life.rules'}))
        court_reverse_import = (
            source.startswith('cultivation_life.system.court.')
            and source != 'cultivation_life.system.court.wiring'
            and target in COURT_FACADES | {'cultivation_life.system.court.wiring'})
        if (system_to_engine or domain_to_facade or domain_to_wiring
                or shared_definition_cycle or shared_to_consumer or battle_reverse_import
                or core_reverse_import or court_reverse_import):
            invalid.append({'source': source, 'target': target, 'line': line})
    return invalid


def report(root):
    modules, edges = import_edges(root)
    return {'modules': len(modules), 'edges': len(edges), 'cycles': cycles(modules, edges),
            'violations': violations(edges)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--json', type=Path, help='Write the complete import-cycle report')
    args = parser.parse_args()
    result = report(args.root)
    if args.json:
        args.json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({**result, 'cycles': [len(group) for group in result['cycles']]}, ensure_ascii=False))
    return bool(result['violations'] or result['cycles'])


if __name__ == '__main__':
    raise SystemExit(main())
