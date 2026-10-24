"""Pure, declarative major-realm appearance selection; no save or RNG writes."""


def resolve_realm_appearance(forms, realm_index, *, branch=None, variant=None, history=()):
    """Pick the latest eligible form, retaining earlier art between painted stages.

    Callers provide the authoritative physical realm (not a temporary suppression
    level). Branches and variants are opaque keys owned by the content provider.
    Explicit historical alternatives never guess an unrecorded lineage.
    """
    eligible = [row for row in forms
                if row.get('branch', branch) == branch
                and row['min_realm'] <= realm_index <= row.get('max_realm', float('inf'))]
    for row in sorted(eligible, key=lambda r: r['min_realm'], reverse=True):
        choices = row.get('variants')
        if 'history_variants' in row:
            choices = next((row['history_variants'][key] for key in reversed(history)
                            if key in row['history_variants']), None)
        appearance = choices.get(variant, choices.get('shared')) if choices else row.get('appearance')
        if appearance:
            return dict(appearance)
    return None
