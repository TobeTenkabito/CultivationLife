"""One-time translation of legacy serialized domain names; IDs stay stable."""
RENAMES = {"domain": "voisinage", "domains": "voisinages", "domain_ids": "voisinage_ids", "domain_id": "voisinage_id",
           "active_domain": "active_voisinage", "domain_controlled": "voisinage_controlled",
           "domain_lethal": "voisinage_lethal", "domain_suppressed": "voisinage_suppressed",
           "last_domain_engagement": "last_voisinage_engagement"}


def migrate(value):
    if isinstance(value, list):
        return [migrate(row) for row in value]
    if isinstance(value, dict):
        return {RENAMES.get(key, key): ("voisinage" if key == "initiative" and row == "domain" else migrate(row))
                for key, row in value.items() if key not in RENAMES or RENAMES[key] not in value}
    return value
