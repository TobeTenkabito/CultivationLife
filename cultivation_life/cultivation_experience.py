"""Shared personal growth grants used by normal training and manual secrets."""
import math

from .content_registry import WORLD_SYSTEMS
from .technique_requirements import QI_NAMES

ART_NAMES = {'alchemy':'炼丹', 'refining':'炼器', 'formation':'阵法',
             'talisman':'制符', 'spirit_control':'御灵'}


def body_progress_required(player):
    config = WORLD_SYSTEMS['body_cultivation']
    return float(config['progress_base']) + player.body_training * float(config['progress_per_layer'])


def grant_body_progress(player, amount):
    gained = max(0., min(float(amount), body_progress_required(player) - player.body_progress))
    player.body_progress += gained
    if player.body_progress >= body_progress_required(player):
        player.awaiting_body_breakthrough = True
    return gained


def grant_qi_mastery(player, source, amount):
    if source not in QI_NAMES or not math.isfinite(amount) or amount < 0:
        raise ValueError('气经验来源或增量无效')
    player.qi_experience[source] = player.qi_experience.get(source, 0.) + amount
    return amount


def art_experience_gain(player, art_id, amount):
    if art_id not in ART_NAMES or not math.isfinite(amount) or amount <= 0:
        return 0.
    if art_id == 'alchemy':
        amount *= 1 + max(0., float(player.sage_effects.get('field_alchemy_multiplier', 0.)))
    if art_id in {'refining','formation'}:
        amount *= 1 + max(0., float(player.sage_effects.get('crafting_formation_multiplier', 0.)))
    return amount * (1 + max(0., float(player.sage_effects.get('art_experience_multiplier', 0.))))


def grant_art_experience(player, art_id, amount):
    gain = art_experience_gain(player, art_id, amount)
    if gain:
        player.art_experience[art_id] = float(player.art_experience.get(art_id, 0.)) + gain
    return gain
