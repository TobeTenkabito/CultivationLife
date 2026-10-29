"""Unlocked cosmetic identities; never substitute cultivation or combat statistics."""
from . import content_registry as registry
from .character_visuals import character_appearance
from .monster_visuals import monster_appearance, _appearance
from .visual_assets import public_catalog


def _assets():
    return public_catalog(registry.default_content_root().parent, registry.EXTENSION_REPORT,
                          registry.default_extension_root())['assets']


def _blocked(player):
    return bool(player.ghost_host_body or player.ghost_attachment or
                player.transformation_loadouts.get(getattr(player.transformation_technique, 'id', None), {}).get('active'))


def natural_appearance(player):
    return monster_appearance(player) or character_appearance(player)


def _attained_realm(player):
    return max(player.realm_index, (player.sealed_cultivation or {}).get('realm_index', 0),
               (player.cultivation_suppression or {}).get('realm_index', 0))


def _matches(player, form):
    # Explicit cosmetic scope, never a wildcard for natural/bloodline forms.
    if form.get('scope') == 'all_paths':
        return form.get('gender') == player.gender
    if form.get('scope') == 'path':
        return form.get('gender') == player.gender and form.get('path') == player.path
    return all(form.get(k) == getattr(player, k) for k in ('path', 'race', 'gender'))


def _skin_entry(key, form, assets):
    return dict(id=key, static=key, combat=form.get('combat'), name=form.get('name', key),
                thumbnail=assets.get(key+'.thumbnail', assets[key+'.figure'])['file'],
                unlock_label=form.get('unlock_label', ''))


def _catalog_forms(assets):
    forms = {}
    for entry in assets.values():
        for form in entry.get('character_forms', []):
            if form.get('role') == 'hero':
                forms[form['static']] = dict(form)
        for form in entry.get('skin_forms', []):
            forms[form['static']] = dict(form)
        if entry.get('appearance_key'):
            from .monster_visuals import _read
            from .visual_assets import extension_asset
            path = extension_asset(registry.default_content_root().parent, registry.default_extension_root(),
                                   registry.EXTENSION_REPORT, entry['file'])
            data = _read(path)
            def collect(value):
                if isinstance(value, dict):
                    if 'static' in value and str(value['static']).startswith('actor.monster.'):
                        key = value['static']
                        actor = data.get('actors', {}).get(value.get('combat'), {})
                        forms[key] = dict(value, name=actor.get('name', '血脉形貌'), monster_node=True)
                    else:
                        for child in value.values():
                            collect(child)
                elif isinstance(value, list):
                    for child in value:
                        collect(child)
            collect(data.get('realm_forms', []))
    return forms


def eligible_skins(player):
    """Attained forms, bloodline history and explicit universal cosmetic unlocks."""
    assets = _assets()
    forms = _catalog_forms(assets)
    unlocked = set(player.character_skins.get('unlocked', []))
    if not _blocked(player):
        realm = _attained_realm(player)
        for key, form in forms.items():
            if (_matches(player, form)
                    and form.get('min_realm_index', 0) <= realm and not form.get('monster_node')
                    and not form.get('achievement')):
                unlocked.add(key)
        if player.path == 'monster':
            for node in dict.fromkeys([*player.monster_evolution_history, player.monster_evolution_id]):
                appearance = _appearance(player, player.monster_species_id, node_id=node)
                if appearance:
                    key = appearance['static']
                    forms[key] = dict(appearance, name=registry.MONSTER_EVOLUTIONS.get(node, {}).get('name', '妖修形貌'))
                    unlocked.add(key)
    # Persisted monster forms are reconstructed only from currently loaded artwork.
    for key in unlocked:
        if key not in forms and key+'.figure' in assets:
            for entry in assets.values():
                for skin in entry.get('skin_forms', []):
                    if skin['static'] == key:
                        forms[key] = skin
    result = []
    for key in sorted(unlocked):
        form = forms.get(key)
        if form and form.get('scope') in {'all_paths', 'path'} and not _matches(player, form):
            continue
        if form and key+'.portrait' in assets and key+'.figure' in assets:
            result.append(_skin_entry(key, form, assets))
    return result


def unlock_achievement_rewards(player, achievements):
    """Grant only cosmetic identities authorized by the existing global ledger."""
    earned = {key for key, form in _catalog_forms(_assets()).items()
              if form.get('achievement') in achievements and _matches(player, form)}
    unlocked = sorted(set(player.character_skins.get('unlocked', [])) | earned)
    if unlocked == player.character_skins.get('unlocked', []):
        return False
    player.character_skins = {**player.character_skins, 'unlocked': unlocked}
    return True


def remember(player):
    if _blocked(player):
        return False
    unlocked = sorted(set(player.character_skins.get('unlocked', [])) | {s['id'] for s in eligible_skins(player)})
    if unlocked == player.character_skins.get('unlocked', []):
        return False
    player.character_skins = {**player.character_skins, 'unlocked': unlocked}
    return True


def appearance(player):
    if not _blocked(player):
        selected = player.character_skins.get('selected')
        if selected:
            skin = next((s for s in eligible_skins(player) if s['id'] == selected), None)
            if skin:
                return dict(static=skin['static'], combat=skin['combat'])
    return natural_appearance(player)


def public(player):
    available = eligible_skins(player)
    known = {skin['id'] for skin in available}
    assets = _assets()
    locked = [_skin_entry(form['static'], form, assets) for entry in assets.values()
              for form in entry.get('skin_forms', [])
              if form.get('scope') in {'all_paths', 'path'} and _matches(player, form) and form['static'] not in known
              and (form.get('achievement') or form.get('min_realm_index', 0) > _attained_realm(player))
              and form['static']+'.portrait' in assets and form['static']+'.figure' in assets]
    return dict(selected=player.character_skins.get('selected'), available=available,
                locked=locked, blocked=_blocked(player))


def choose(player, identity):
    if not isinstance(identity, str):
        raise ValueError('皮肤编号无效')
    if _blocked(player):
        raise ValueError('请先结束寄身、附身或变化形态，再切换皮肤')
    options = eligible_skins(player)
    if identity and identity not in {s['id'] for s in options}:
        raise ValueError('该皮肤尚未解锁或所属内容包未启用')
    remember(player)
    player.character_skins['selected'] = identity or None


