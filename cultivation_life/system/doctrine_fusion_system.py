"""Player-triggered fusion and elapsed study; no NPC or yearly scans."""
from ..models import Technique, HistoryRecord
from ..rules import learn_technique
from .doctrine.provider import player_record, config
from .doctrine.fusion import eligible, manual_id, compile_manual


class DoctrineFusionMixin:
    def _fusion_requirements(self, game, key, *, study=False):
        p, record = game.player, player_record(game)
        definition = game.doctrine_state['definitions'].get(key)
        if p.world != 'celestial' or not p.immortal_power_converted or p.sealed_cultivation or p.cultivation_suppression:
            raise ValueError('合练参悟须在仙界完成仙灵力转化，且修为未受压制')
        if not definition or not eligible(definition):
            raise ValueError('此道统不足六部原始功法，不能合练')
        fusion = record.get('fusion', {}).get(key)
        if study:
            if not fusion or fusion['level'] >= 9:
                raise ValueError('须先合练，且合练功法尚未满级')
            if not any(t.id == manual_id(key) for t in p.known_techniques):
                raise ValueError('尚未掌握合练功法')
        elif fusion:
            raise ValueError('此道统已经合练，不可重复生成')
        else:
            known = {t.id for t in p.known_techniques}
            if any(b['id'] not in known for b in definition['manuals']):
                raise ValueError('须先集齐并学会本门全部原始功法')
        if p.realm_index < max(b['grade'] for b in definition['manuals']):
            raise ValueError('修为尚不足以合练本门最高品阶传承')
        return definition, fusion

    def _fuse_doctrine(self, game, key):
        definition, _ = self._fusion_requirements(game, key)
        cost = config()['cultivation']['fusion']['creation_traces']
        if game.player.immortal_traces < cost:
            raise ValueError('合练所需仙痕不足')
        manual = Technique(**compile_manual(game.seed, definition, config()['words']))
        learn_technique(game.player, manual)
        game.player.immortal_traces -= cost
        player_record(game).setdefault('fusion', {})[key] = dict(level=1, experience=0)
        return self._save_cultivation(game, f"融汇《{definition['name']}》全套传承，合练成《{manual.name}》Lv1；原有功法保留，后续在道统界面参悟。")

    def _begin_fusion_study(self, game, *, commit=False):
        record = player_record(game)
        _, fusion = self._fusion_requirements(game, record.get('fusion_target'), study=True)
        cost = config()['cultivation']['fusion']['study_traces_per_level'] * (fusion['level'] + 1)
        if not fusion.get('paid'):
            if game.player.immortal_traces < cost:
                raise ValueError('参悟合练功法所需仙痕不足')
            if commit:
                game.player.immortal_traces -= cost
                fusion['paid'] = True

    def _finish_fusion_study(self, game, elapsed):
        record = player_record(game)
        key = record['fusion_target']
        fusion = record['fusion'][key]
        if not fusion.get('paid') or fusion['level'] >= 9:
            return
        required = config()['level_years'][fusion['level']]
        fusion['experience'] = min(required, fusion.get('experience', 0) + elapsed)
        if fusion['experience'] < required:
            return
        fusion.update(level=fusion['level'] + 1, experience=0, paid=False)
        p = game.player
        for book in [*p.known_techniques, p.technique, p.support_technique, *p.combat_techniques]:
            if book and book.id == manual_id(key):
                book.level = fusion['level']
        game.history.append(HistoryRecord('SYS_DOCTRINE_FUSION_STUDY', 1, p.age, '参悟合练功法', key,
            'completed', f"合练功法参悟至 Lv{fusion['level']}，无需外求玉简；道统层级仍须另行参悟。", {}, ['system','doctrine']))

    def _public_fusion(self, game, definition):
        if not eligible(definition):
            return None
        key = definition['id']
        p, record = game.player, player_record(game)
        known = {t.id for t in p.known_techniques}
        books = definition['manuals']
        owned = sum(b['id'] in known for b in books)
        fusion = record.get('fusion', {}).get(key, {})
        level = fusion.get('level', 0)
        cost = config()['cultivation']['fusion']['creation_traces'] if not level else (
            0 if fusion.get('paid') else config()['cultivation']['fusion']['study_traces_per_level'] * (level+1))
        manual = next((t for t in p.known_techniques if t.id == manual_id(key)), None)
        permitted = bool(p.immortal_power_converted and not p.sealed_cultivation and not p.cultivation_suppression
                         and p.realm_index >= max(b['grade'] for b in books) and p.immortal_traces >= cost)
        return dict(total=len(books), owned=owned, level=level, name=manual.name if manual else None,
                    cost=cost, experience=fusion.get('experience', 0),
                    required=config()['level_years'][level] if 0 < level < 9 else 0,
                    can_fuse=not level and owned == len(books) and permitted,
                    can_study=0 < level < 9 and permitted,
                    effect_level=min(level, record['progress'].get(key, {}).get('level', 0)))
