"""Optional character art from loaded package declarations; never alters people/RNG."""
from . import content_registry as registry
from .visual_assets import public_catalog


def character_appearance(person, *, role='hero'):
    def value(key, default=None):
        return person.get(key, default) if isinstance(person, dict) else getattr(person, key, default)
    if (value('gender') not in {'male', 'female'} or value('identity_known', True) is False
            or value('ghost_host_body') or value('ghost_attachment') or value('host_body')
            or value('possession') or value('transformed')
            or value('lineage_race') and value('lineage_race') != value('race')):
        return None
    technique = value('transformation_technique')
    technique_id = technique.get('id') if isinstance(technique, dict) else getattr(technique, 'id', None)
    if value('transformation_loadouts', {}).get(technique_id, {}).get('active'):
        return None
    # These packages currently supply adult human-origin forms only.
    if role == 'npc' and value('age', 18) < 18:
        return None
    assets = public_catalog(registry.default_content_root().parent, registry.EXTENSION_REPORT,
                            registry.default_extension_root())['assets']
    for row in assets.values():
        for form in row.get('character_forms', []):
            if (all(form.get(key) == value(key) for key in ('path','race','gender'))
                    and form.get('role') == role and form.get('combat') in row.get('combat_actors', [])
                    and form.get('static', '')+'.portrait' in assets
                    and form.get('static', '')+'.figure' in assets):
                return dict(static=form['static'], combat=form['combat'])
    return None
