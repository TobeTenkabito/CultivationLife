"""Inventory movement sites and reject direct player-world writes outside the boundary.

AST coverage includes aliases named player/p and <expression>.player, tuple
assignment and setattr. Snapshot editors and generic NPC writers require manual
review; this check deliberately does not claim whole-program alias analysis.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_PLAYER_WRITES = {
    ('cultivation_life/engine/orchestration/session.py', 'create_game'),
    ('cultivation_life/system/world_transition_system.py', 'apply_world_transition'),
}


def player_expression(node):
    return (isinstance(node, ast.Name) and node.id in {'p', 'player'}
            or isinstance(node, ast.Attribute) and node.attr == 'player')


def inventory(root=ROOT):
    writes, calls, fields = [], [], {}
    for path in sorted((root / 'cultivation_life').rglob('*.py')):
        relative = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for cls in tree.body:
            if isinstance(cls, ast.ClassDef) and cls.name in {'Player', 'GameState'}:
                fields[cls.name] = [n.target.id for n in cls.body if isinstance(n, ast.AnnAssign)
                                    and isinstance(n.target, ast.Name)]

        class Scan(ast.NodeVisitor):
            function = '<module>'

            def visit_FunctionDef(self, node):
                previous = self.function
                self.function = node.name
                self.generic_visit(node)
                self.function = previous

            def visit_Attribute(self, node):
                if node.attr == 'world' and isinstance(node.ctx, ast.Store):
                    writes.append(dict(file=relative, function=self.function, line=node.lineno,
                                       expression=ast.unparse(node), player=bool(player_expression(node.value))))
                self.generic_visit(node)

            def visit_Call(self, node):
                name = ast.unparse(node.func)
                if any(key in name for key in ('world_transition', 'move_world', 'enter_scene', 'spatial_action')):
                    calls.append(dict(file=relative, function=self.function, line=node.lineno, call=name))
                if (name == 'setattr' and len(node.args) >= 3 and isinstance(node.args[1], ast.Constant)
                        and node.args[1].value == 'world' and player_expression(node.args[0])):
                    writes.append(dict(file=relative, function=self.function, line=node.lineno,
                                       expression=ast.unparse(node), player=True))
                self.generic_visit(node)
        Scan().visit(tree)
    content = json.loads((root / 'content/world.json').read_text(encoding='utf-8'))['systems']
    errors = [row for row in writes if row['player'] and (row['file'], row['function']) not in ALLOWED_PLAYER_WRITES]
    return dict(player_and_npc_world_writes=writes, movement_calls=calls,
                routes=content['world_transition_routes'], state_fields=fields, errors=errors)


if __name__ == '__main__':
    report = inventory()
    output = ROOT / 'build/world-transition-audit-211.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Cross-world contract: {len(report['movement_calls'])} movement call sites, "
          f"{len(report['routes'])} routes, {sum(map(len, report['state_fields'].values()))} state fields, "
          f"{len(report['errors'])} forbidden player-world writes. Inventory: {output}")
    for row in report['errors']:
        print(row)
    raise SystemExit(bool(report['errors']))
