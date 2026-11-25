"""Distinct personal traits expressed in the ordinary battle's existing event vocabulary."""
from .definition_data import definition as _content_definition
from .trait_lineages import LINEAGES
from .trait_repertoires import REPERTOIRES
from .trait_rule_builders import Signature


SIGNATURES = _content_definition(__name__, "SIGNATURES", Signature)


SIGNATURES.update({key: entry.signature for key, entry in REPERTOIRES.items()})


def combat_rules(traits):
    return tuple(dict(step, schema_version=3, source_id="特质·" + LINEAGES[key].name)
                 for key in traits if key in SIGNATURES for step in SIGNATURES[key].rules)
