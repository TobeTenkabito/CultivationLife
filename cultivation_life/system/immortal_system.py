"""Player-only vein and voisinage cultivation actions; no annual NPC hooks."""
from ..content_registry import REALMS
from ..models import HistoryRecord
from ..rules import remove_item, public_player
from ..runtime import now_iso, decode_rng, encode_rng
from .doctrine.provider import config, ensure, player_record
from .doctrine.cultivation import AXES, vein_cost, training_cost


def item_quantity(player, item_id):
    return sum(item.quantity for item in player.inventory if item.id == item_id)


class ImmortalCultivationMixin:
    def _cultivation_game(self, game_id):
        game = self._load(game_id)
        p = game.player
        if p.world != "celestial" or p.realm_index < 9:
            raise ValueError("须在仙界达到真仙境界")
        if (not p.alive or game.pending_event or game.active_trial or p.imprisonment
                or p.ghost_captor or game.heavenly_court.get("open_election")
                or (game.guixu_state.get("player_session") or {}).get("trapped")):
            raise ValueError("当前状态无法修持，请先处理事件或脱离拘束")
        ensure(game)
        return game

    def _save_cultivation(self, game, summary):
        game.history.append(HistoryRecord("SYS_IMMORTAL_CULTIVATION", 1, game.player.age,
                                         "仙道修持", None, "completed", summary, {}, ["system", "cultivation"]))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def immortal_action(self, game_id, action, doctrine_id=None, axis=None):
        game = self._cultivation_game(game_id)
        p, record, rules = game.player, player_record(game), config()["cultivation"]
        if action == "gather":
            return self.advance(game_id, "immortal_trace_gather", 1)
        if not p.immortal_power_converted:
            raise ValueError("须先完成仙灵力转化")
        opened = p.immortal_veins.get(str(p.realm_index), 0)
        if action == "open_vein":
            if opened >= rules["veins_per_realm"]:
                raise ValueError("本境仙脉已经全部开启")
            cost = vein_cost(p.realm_index, opened, rules)
            self._spend_cultivation(p, cost)
            p.immortal_veins[str(p.realm_index)] = opened + 1
            layer = min(9, 1 + (opened + 1) // rules["veins_per_layer"])
            if layer > p.layer:
                rng = decode_rng(game.seed, game.rng_state)
                self._complete_minor_breakthrough(game, rng, public_player(p)["realm_name"])
                game.rng_state = encode_rng(rng)
            summary = f"开启本境第 {opened + 1}/27 条仙脉，当前{public_player(p)['realm_name']}。"
        elif action == "breakthrough":
            if opened < rules["veins_per_realm"] or p.layer < 9:
                raise ValueError("须先开启本境全部 27 条仙脉")
            if p.realm_index >= len(REALMS) - 1:
                raise ValueError("已达当前开放的最高大境界")
            rng = decode_rng(game.seed, game.rng_state)
            self._complete_major_breakthrough(game, rng, public_player(p)["realm_name"])
            game.rng_state = encode_rng(rng)
            summary = f"二十七脉贯通，进阶{public_player(p)['realm_name']}。机缘余量保留。"
        elif action == "train_voisinage":
            level = record["progress"].get(doctrine_id, {}).get("level", 0)
            if level < 4 or axis not in AXES:
                raise ValueError("须选择已激发的邻域与有效培养维度")
            training = record.setdefault("voisinage_training", {}).setdefault(doctrine_id, {})
            rank = training.get(axis, 0)
            if rank >= rules["voisinage_max_training"]:
                raise ValueError("此维度已达当前培养上限")
            self._spend_cultivation(p, training_cost(rank, rules))
            training[axis] = rank + 1
            summary = f"温养邻域：{ {'stability':'稳固','incursion':'侵夺','authority':'权能'}[axis]}达到 {rank + 1} 重。"
        else:
            raise ValueError("未知仙道修持操作")
        return self._save_cultivation(game, summary)

    @staticmethod
    def _spend_cultivation(player, cost):
        if player.opportunity < cost["opportunity"] or item_quantity(player, "immortal_trace") < cost["traces"]:
            raise ValueError("机缘或仙痕不足")
        remove_item(player, "immortal_trace", cost["traces"])
        player.opportunity -= cost["opportunity"]

    @staticmethod
    def _public_immortal(game):
        rules, p = config()["cultivation"], game.player
        opened = p.immortal_veins.get(str(p.realm_index), 0)
        return {"opened": opened, "total": rules["veins_per_realm"], "per_layer": rules["veins_per_layer"],
                "realm": REALMS[p.realm_index].name, "layer": p.layer, "opportunity": p.opportunity,
                "traces": item_quantity(p, "immortal_trace"), "converted": p.immortal_power_converted,
                "next_cost": vein_cost(p.realm_index, opened, rules) if opened < rules["veins_per_realm"] else None,
                "can_breakthrough": opened >= rules["veins_per_realm"] and p.realm_index < len(REALMS) - 1,
                "trace_years": rules["trace_years"]}
