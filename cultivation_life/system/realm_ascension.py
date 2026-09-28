"""Base-world ascension routes; optional paths may override these defaults."""
from .path_modifiers import register_provider


def realm_ascension_modifier(subject, key, **context):
    player = getattr(subject, "player", subject)
    if player.world != "hell":
        return None
    if key == "ascension_source":
        return True
    if key == "ascension_destination":
        return "reincarnation"
    if key == "ascension_events":
        return [f"EVT_REINCARNATION_ASCENSION_{i:03d}" for i in range(1, 10)]


register_provider("world.ascension", realm_ascension_modifier)
