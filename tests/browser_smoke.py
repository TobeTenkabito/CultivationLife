"""Manual browser smoke test; uses a temporary database only."""

from __future__ import annotations

import tempfile
import threading
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cultivation_life import (  # noqa: E402
    ChangeContribution,
    EnterConcubineStatus,
    EnterImprisonment,
    FormRelationship,
    GrantTechnique,
    RegisterCharacter,
    ResolveCombat,
)
from cultivation_life.application import GameEngine  # noqa: E402
from cultivation_life.domain.celestial import (  # noqa: E402
    CELESTIAL_COURT,
    reconcile_celestial_state,
)
from cultivation_life.domain.economy import GrantItem  # noqa: E402
from cultivation_life.server import build_handler  # noqa: E402


def assert_visible_panels_clean(page) -> None:
    visible_targets = page.locator("[data-panel-target]:visible")
    for index in range(visible_targets.count()):
        button = visible_targets.nth(index)
        target = button.get_attribute("data-panel-target")
        panel = page.locator(f"#{target}-card")
        assert panel.count() == 1, target
        if panel.evaluate("node => node.classList.contains('hidden')"):
            continue
        if not panel.evaluate("node => node.classList.contains('panel-open')"):
            button.click(force=True)
        if not panel.evaluate("node => node.classList.contains('panel-open')"):
            button.click(force=True)
        assert panel.evaluate("node => node.classList.contains('panel-open')"), target
        panel_text = panel.inner_text()
        assert "NaN" not in panel_text, (target, panel_text)
        assert "undefined" not in panel_text, (target, panel_text)
        assert "null" not in panel_text, (target, panel_text)


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        engine = GameEngine(
            Path(temporary) / "games.db",
            content_directory=ROOT / "content",
            extension_root=ROOT,
        )
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), build_handler(engine, ROOT / "web")
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors: list[str] = []
                console_errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on(
                    "console",
                    lambda message: (
                        console_errors.append(message.text)
                        if message.type == "error"
                        else None
                    ),
                )
                response = page.goto(f"http://127.0.0.1:{server.server_port}/")
                assert response is not None and response.ok

                assert page.locator("#start-extension-manager").count() == 1
                assert page.locator("#start-extension-list input[type=checkbox]").count() > 0
                assert page.locator("#quick-start-list button").count() == 9
                page.locator("#new-game-form input[name=name]").fill("快速开局烟测")
                with page.expect_response(
                    lambda item: item.url.endswith("/api/games")
                    and item.request.method == "POST"
                ) as pending:
                    page.locator(
                        '.quick-start-button[data-preset-id="core"]'
                    ).click()
                assert pending.value.status == 201, pending.value.text()
                page.locator("#game-screen").wait_for(state="visible")
                assert "结丹" in page.locator("#realm-name").text_content()
                assert "混元抱丹书" in page.locator(
                    "#known-technique-list"
                ).text_content()
                page.locator("#new-game-button").click()
                page.locator("#start-screen").wait_for(state="visible")
                page.locator("#path-select").select_option("monster")
                assert page.locator("#monster-species-field").is_visible()
                assert page.locator("#monster-species-select option").count() == 8
                page.locator("#path-select").select_option("dao")
                page.locator("#achievement-open").click()
                page.locator(".achievement-row").first.wait_for(state="visible")
                assert page.locator(".achievement-row").count() == 58
                page.locator("#achievement-close").click()

                page.locator("#new-game-form input[name=name]").fill("界面烟测")
                page.locator("#path-select").select_option("demonic")
                page.locator("#new-game-form button[type=submit]").click()
                page.locator("#game-screen").wait_for(state="visible")
                assert page.locator("nav.left-dock button").count() == 12
                assert page.locator("#strategy-dock button").count() == 14
                assert page.locator("nav.settings-dock button").count() == 1
                assert page.locator("#map-locations .map-location").count() >= 2
                assert "NaN" not in page.locator("body").inner_text()
                assert "undefined" not in page.locator("body").inner_text()
                technique_text = page.locator("#known-technique-list").text_content()
                assert "魔煞引气诀" in technique_text
                assert "魔源" in technique_text
                assert "机缘 +10%" in technique_text
                assert page.locator("#player-race").text_content() == "人族"

                game_id = str(page.evaluate("game.id"))
                state = engine.store.load(game_id)
                actor_id = str(state.controlled_entity_id)
                cultivation = state.entities.require(actor_id, "cultivation.state")
                cultivation.update(
                    realm_id="core", layer=1, opportunity=300.0, bottleneck="minor"
                )
                state.entities.put(actor_id, "cultivation.state", cultivation)
                engine.store.save(
                    state, [], player_name="界面烟测", expected_revision=state.revision
                )
                page.evaluate("id => loadGame(id)", game_id)
                page.locator("body:not(.busy)").wait_for()
                assert "初期·1层" in page.locator("#realm-name").text_content()
                assert "53%" in page.locator("#breakthrough-reason").text_content()
                assert "基础 48%" in page.locator("#breakthrough-reason").text_content()

                engine.execute(
                    game_id,
                    GrantItem(actor_id, "spirit_stone", 10**9, "browser-smoke"),
                )
                engine.execute(
                    game_id,
                    GrantItem(
                        actor_id, "star_pattern_copper", 1,
                        "browser-smoke",
                    ),
                )
                engine.execute(
                    game_id,
                    GrantTechnique(
                        actor_id, "TECH_BLOOD_SHADOW_TRANSFORMATION"
                    ),
                )
                engine.equip_special_technique(
                    game_id, "TECH_BLOOD_SHADOW_TRANSFORMATION",
                    "transformation",
                )
                engine.execute(
                    game_id,
                    GrantItem(
                        actor_id, "phoenix_soul_flame", 6,
                        "browser-smoke",
                    ),
                )
                # Seed concrete instance assets, then drive the frozen V1
                # controls themselves.  This catches response-shape and
                # reservation bugs that direct engine tests cannot see.
                asset_state = engine.store.load(game_id)
                ledger = asset_state.entities.require(
                    actor_id, "economy.asset_ledger"
                )
                instances = dict(ledger["instances"])

                def add_asset(kind, definition, metadata):
                    sequence = int(ledger["next_sequence"])
                    asset_id = f"asset:{actor_id}:{sequence}"
                    instances[asset_id] = {
                        "id": asset_id, "kind": kind,
                        "definition_id": definition["id"],
                        "name": definition["name"],
                        "created_year": asset_state.clock.year,
                        "metadata": metadata, "reservation_id": None,
                    }
                    ledger["next_sequence"] = sequence + 1
                    return asset_id

                craft_defs = engine.definitions.systems["crafting"]["materials"]
                primary_def = next(
                    row for row in craft_defs if "primary" in row["roles"]
                )
                secondary_defs = [
                    row for row in craft_defs if "secondary" in row["roles"]
                ]
                secondary_a_def = secondary_defs[0]
                secondary_b_def = next(
                    row for row in secondary_defs
                    if row["id"] != secondary_a_def["id"]
                    or row.get("allow_duplicate_type")
                )
                quench_def = next(
                    row for row in craft_defs if "quench" in row["roles"]
                )
                craft_ids = []
                for definition in (
                    primary_def, secondary_a_def,
                    secondary_b_def, quench_def,
                ):
                    craft_ids.append(add_asset(
                        "crafting_material", definition,
                        {
                            "tier": definition.get("tier", 1),
                            "quality_multiplier": 1.0,
                            "material_value": definition["base_material_value"],
                            "source": "browser-smoke",
                        },
                    ))
                formation_def = engine.definitions.systems[
                    "formations"
                ]["materials"][0]
                formation_ids = [
                    add_asset(
                        "formation_material", formation_def,
                        {
                            "tier": formation_def["tier"],
                            "base_value": formation_def["base_value"],
                            "formation_value": formation_def["formation_value"],
                            "nature": formation_def["nature"],
                            "source": "browser-smoke",
                        },
                    )
                    for _ in range(2)
                ]
                repair_def = next(
                    row for row in engine.definitions.systems[
                        "formations"
                    ]["maintenance_resources"]
                    if row["world"] == "human"
                )
                add_asset(
                    "formation_supply", repair_def,
                    {
                        "tier": repair_def["tier"],
                        "base_value": repair_def["base_value"],
                        "repair_value": repair_def["repair_value"],
                        "source": "browser-smoke",
                    },
                )
                ledger["instances"] = instances
                asset_state.entities.put(
                    actor_id, "economy.asset_ledger", ledger
                )
                engine.store.save(
                    asset_state, [], player_name="界面烟测",
                    expected_revision=asset_state.revision,
                )
                page.evaluate("id => loadGame(id)", game_id)
                page.locator("body:not(.busy)").wait_for()

                page.locator(
                    '[data-panel-target="transformation"]'
                ).click(force=True)
                assert "血影化魔经" in page.locator(
                    "#transformation-summary"
                ).text_content()
                material = page.locator(
                    "#transformation-materials .transformation-material"
                ).filter(has_text="凤凰元神火")
                assert material.count() == 1
                material.locator("select").select_option("sustain")
                with page.expect_response(
                    lambda item: item.url.endswith("/transformation-absorb")
                ) as pending:
                    material.get_by_role(
                        "button", name="炼化", exact=True
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                material = page.locator(
                    "#transformation-materials .transformation-material"
                ).filter(has_text="凤凰元神火")
                material.locator("select").select_option("might")
                with page.expect_response(
                    lambda item: item.url.endswith("/transformation-purify")
                ) as pending:
                    material.get_by_role(
                        "button", name="两份合炼提纯"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                material = page.locator(
                    "#transformation-materials .transformation-material"
                ).filter(has_text="凤凰元神火")
                material.locator("select").select_option("guard")
                with page.expect_response(
                    lambda item: item.url.endswith("/transformation-batch")
                ) as pending:
                    material.get_by_role("button", name="一键合炼").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                known_form = page.locator(
                    "#transformation-known .transformation-form"
                ).filter(has_text="凤凰变")
                known_form.wait_for(state="visible")
                assert known_form.locator(
                    ".transformation-stat-bar"
                ).count() == 6
                with page.expect_response(
                    lambda item: item.url.endswith("/transformation")
                ) as pending:
                    known_form.get_by_role("button", name="存入").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                stored_form = page.locator(
                    "#transformation-stored .transformation-form"
                ).filter(has_text="凤凰变")
                with page.expect_response(
                    lambda item: item.url.endswith("/transformation")
                ) as pending:
                    stored_form.get_by_role("button", name="启用").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert "权重 100%" in page.locator(
                    "#transformation-stored"
                ).text_content()
                assert page.locator(
                    "#transformation-combined .transformation-stat"
                ).count() == 6

                assert page.locator(
                    '[data-panel-target="crafting"]'
                ).is_visible()
                page.locator('[data-panel-target="crafting"]').click(force=True)
                page.locator("#crafting-primary").select_option(craft_ids[0])
                page.locator("#crafting-secondary-a").select_option(craft_ids[1])
                page.locator("#crafting-secondary-b").select_option(craft_ids[2])
                page.locator("#crafting-quench").select_option(craft_ids[3])
                page.locator(
                    '#crafting-allocations input[data-stat="combat_power"]'
                ).fill("1")
                with page.expect_response(
                    lambda item: item.url.endswith("/crafting-preview")
                ) as pending:
                    page.locator("#crafting-preview").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator(
                    "#crafting-preview-result button"
                ).wait_for(state="visible")
                assert "锚定价值" in page.locator(
                    "#crafting-preview-result"
                ).inner_text()
                with page.expect_response(
                    lambda item: item.url.endswith("/crafting-blueprint")
                ) as pending:
                    page.locator("#crafting-save-blueprint").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.locator(
                    "#crafting-blueprint-list .crafting-blueprint"
                ).count() == 1
                page.locator(
                    "#crafting-blueprint-list .crafting-blueprint"
                ).click()
                with page.expect_response(
                    lambda item: item.url.endswith("/crafting-preview")
                ) as pending:
                    page.locator("#crafting-preview").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator(
                    "#crafting-preview-result button"
                ).wait_for(state="visible")
                page.locator("#crafting-preview-result button").click()
                with page.expect_response(
                    lambda item: item.url.endswith("/crafting-forge")
                ) as pending:
                    page.locator("#game-confirm-accept").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                page.locator('[data-panel-target="inventory"]').click(force=True)
                assert page.locator(
                    "#inventory-list .crafted-artifact-item"
                ).count() == 1
                assert page.locator(
                    "#inventory-list .crafted-artifact-tools button"
                ).count() >= 2
                page.locator(
                    "#inventory-list .crafted-artifact-tools button"
                ).first.click()
                with page.expect_response(
                    lambda item: item.url.endswith("/crafted-artifact")
                ) as pending:
                    page.locator("#game-confirm-accept").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                page.locator(
                    '[data-panel-target="natal-artifact"]'
                ).click(force=True)
                assert page.locator(
                    "#natal-artifact-card .natal-slot"
                ).count() == 7
                assert page.locator(
                    "#natal-artifact-card .natal-slot:not(.locked)"
                ).count() == 2
                page.locator(
                    "#natal-artifact-card .natal-slot:not(.locked):not(.filled)"
                ).first.click()
                socket_choice = page.locator(
                    ".natal-material-choice[data-natal-unavailable='0']"
                ).first
                assert socket_choice.is_enabled()
                with page.expect_response(
                    lambda item: item.url.endswith("/natal-artifact")
                ) as pending:
                    socket_choice.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.locator(
                    "#natal-artifact-card .natal-slot.filled"
                ).count() == 1

                assert page.locator(
                    '[data-panel-target="formation"]'
                ).is_visible()
                page.locator('[data-panel-target="formation"]').click(force=True)
                formation_selects = page.locator("#formation-grid select")
                formation_selects.nth(0).select_option(formation_ids[0])
                formation_selects.nth(1).select_option(formation_ids[1])
                page.locator("#formation-name").fill("浏览器验真阵")
                with page.expect_response(
                    lambda item: item.url.endswith("/formation-preview")
                ) as pending:
                    page.locator("#formation-preview").click()
                assert pending.value.status == 200, pending.value.text()
                assert "浏览器验真阵" in page.locator(
                    "#formation-effects"
                ).inner_text()
                with page.expect_response(
                    lambda item: item.url.endswith("/formation-save")
                ) as pending:
                    page.locator("#formation-save-activate").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert not page.locator("#formation-deactivate").is_disabled()
                page.locator("#formation-deactivate").click()
                with page.expect_response(
                    lambda item: item.url.endswith("/formation-deactivate")
                ) as pending:
                    page.locator("#game-confirm-accept").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                loadout = page.locator(
                    "#formation-loadout-list .formation-loadout"
                ).filter(has_text="浏览器验真阵")
                with page.expect_response(
                    lambda item: item.url.endswith("/formation-activate")
                ) as pending:
                    loadout.get_by_role("button", name="启阵").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                page.locator("#formation-ground-personal").click()
                with page.expect_response(
                    lambda item: item.url.endswith("/formation-ground-deploy")
                ) as pending:
                    page.locator("#game-confirm-accept").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.locator(
                    "#formation-ground-list .formation-ground-row"
                ).count() == 1
                page.locator(
                    "#map-locations .formation-map-marker"
                ).wait_for(state="attached")
                marker_text = page.locator(
                    "#map-locations .formation-map-marker"
                ).text_content()
                assert "浏览器验真阵" in marker_text, marker_text
                repair_state = engine.store.load(game_id)
                formation_state = repair_state.entities.require(
                    actor_id, "formation.nine_palace"
                )
                formation_state["ground_arrays"][0]["durability"] = 50.0
                repair_state.entities.put(
                    actor_id, "formation.nine_palace", formation_state
                )
                engine.store.save(
                    repair_state, [], player_name="界面烟测",
                    expected_revision=repair_state.revision,
                )
                page.evaluate("id => loadGame(id)", game_id)
                page.locator("body:not(.busy)").wait_for()
                ground_row = page.locator(
                    "#formation-ground-list .formation-ground-row"
                )
                ground_row.locator("select").select_option(repair_def["id"])
                with page.expect_response(
                    lambda item: item.url.endswith(
                        "/formation-ground-repair"
                    )
                ) as pending:
                    ground_row.get_by_role("button", name="修阵").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert "50.0%" not in page.locator(
                    "#formation-ground-list .formation-ground-row"
                ).text_content()
                page.locator(
                    "#formation-ground-list .formation-ground-row"
                ).get_by_role("button", name="撤阵归库").click()
                with page.expect_response(
                    lambda item: item.url.endswith("/formation-ground-withdraw")
                ) as pending:
                    page.locator("#game-confirm-accept").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.locator(
                    "#formation-ground-list .formation-ground-row"
                ).count() == 0
                loadout = page.locator(
                    "#formation-loadout-list .formation-loadout"
                ).filter(has_text="浏览器验真阵")
                loadout.get_by_role("button", name="删除").click()
                with page.expect_response(
                    lambda item: item.url.endswith("/formation-delete")
                ) as pending:
                    page.locator("#game-confirm-accept").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert "浏览器验真阵" not in page.locator(
                    "#formation-loadout-list"
                ).text_content()

                page.locator('[data-panel-target="market"]').click(force=True)
                assert page.locator("#market-offers .market-offer").count() == 6
                assert page.locator(
                    "#material-market-offers .market-offer"
                ).count() == 6
                market_text = page.locator("#market-card").text_content()
                assert "2%" in market_text, market_text
                assert "NaN" not in market_text
                assert "undefined" not in market_text

                material_lock = page.locator(
                    "#material-market-offers .market-lock"
                ).first
                locked_offer_id = material_lock.evaluate(
                    "node => node.closest('.market-offer').querySelector('.market-buy').dataset.offerId"
                )
                with page.expect_response(
                    lambda item: item.url.endswith("/market-lock")
                ) as pending:
                    material_lock.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                locked_row = page.locator(
                    f'#material-market-offers .market-buy[data-offer-id="{locked_offer_id}"]'
                ).locator("xpath=..")
                assert locked_row.locator(".market-lock.active").count() == 1

                buy = page.locator("#market-offers .market-buy:not([disabled])").first
                bought_offer_id = buy.get_attribute("data-offer-id")
                with page.expect_response(
                    lambda item: item.url.endswith("/market-buy")
                ) as pending:
                    buy.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.locator(
                    f'#market-offers .market-buy[data-offer-id="{bought_offer_id}"]'
                ).text_content() == "已售"

                # Reach an actual announced auction through canonical state,
                # then submit the frozen V1 consignment form.  This guards the
                # asset-list field names that a panel-only smoke test cannot
                # see when no auction is active.
                engine.execute(
                    game_id,
                    GrantItem(actor_id, "foundation_pill", 1, "browser-smoke"),
                )
                auction_state = engine.store.load(game_id)
                auction_location = auction_state.entities.require(
                    actor_id, "world.location"
                )["location_id"]
                engine.schedule_auction(game_id, auction_location)
                page.evaluate("id => loadGame(id)", game_id)
                page.locator("body:not(.busy)").wait_for()
                if not page.locator("#auction-card").evaluate(
                    "node => node.classList.contains('panel-open')"
                ):
                    page.locator(
                        '[data-panel-target="auction"]'
                    ).click(force=True)
                consign = page.locator("#auction-consign-item")
                assert consign.locator("option").count() > 0
                consign.select_option("foundation_pill")
                with page.expect_response(
                    lambda item: item.url.endswith("/auction-consign")
                ) as pending:
                    page.locator("#auction-consign-form button[type=submit]").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()

                auction_flow = engine.create_game(
                    "拍卖状态机烟测", seed=771122, preset_id="core"
                )
                auction_game_id = str(auction_flow["id"])
                auction_actor = str(auction_flow["player"]["id"])
                for item_id, quantity in (
                    ("spirit_stone", 10**9),
                    ("foundation_pill", 1),
                    ("healing_pill", 1),
                ):
                    engine.execute(
                        auction_game_id,
                        GrantItem(
                            auction_actor, item_id, quantity, "browser-smoke"
                        ),
                    )
                auction_state = engine.store.load(auction_game_id)
                auction_location = auction_state.entities.require(
                    auction_actor, "world.location"
                )["location_id"]
                engine.schedule_auction(auction_game_id, auction_location)
                engine.consign_auction_asset(
                    auction_game_id, "foundation_pill", 10
                )
                for _ in range(2):
                    engine.perform_action(auction_game_id, "rest", 1)
                    pending_game = engine.get_game(auction_game_id)
                    while pending_game["pending_event"] is not None:
                        choice = next(
                            row for row in pending_game["pending_event"]["choices"]
                            if row["enabled"]
                        )
                        pending_game = engine.choose(
                            auction_game_id, choice["id"]
                        ).game
                pending_game = engine.get_game(auction_game_id)
                assert pending_game["auction"]["status"] == "open", pending_game[
                    "auction"
                ]
                page.evaluate("id => loadGame(id)", auction_game_id)
                page.locator("body:not(.busy)").wait_for()
                if not page.locator("#auction-card").evaluate(
                    "node => node.classList.contains('panel-open')"
                ):
                    page.locator(
                        '[data-panel-target="auction"]'
                    ).click(force=True)
                assert "拍卖会" in page.locator("#auction-title").text_content()

                identity = page.locator(
                    "#auction-identities button:not(.selected)"
                ).first
                with page.expect_response(
                    lambda item: item.url.endswith("/auction-identity")
                ) as pending:
                    identity.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()

                bid = page.locator(
                    "#auction-lots .auction-bid:not([disabled])"
                ).first
                assert bid.count() == 1
                with page.expect_response(
                    lambda item: item.url.endswith("/auction-bid")
                ) as pending:
                    bid.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()

                negotiate = page.locator(
                    "#auction-attendees .auction-attendee button:not([disabled])"
                ).first
                assert negotiate.count() == 1
                with page.expect_response(
                    lambda item: item.url.endswith("/auction-negotiate")
                ) as pending:
                    negotiate.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()

                private_trade = page.locator(
                    "#auction-attendees .private-trade-card"
                ).first
                assert private_trade.count() == 1
                private_trade.locator("summary").click()
                private_offer = private_trade.locator(
                    ".private-trade-offers .auction-lot"
                ).first
                with page.expect_response(
                    lambda item: item.url.endswith(
                        "/auction-private-bargain"
                    )
                ) as pending:
                    private_offer.get_by_role("button", name="讨价").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                private_trade = page.locator(
                    "#auction-attendees .private-trade-card"
                ).first
                private_trade.locator("summary").click()
                private_offer = private_trade.locator(
                    ".private-trade-offers .auction-lot"
                ).first
                with page.expect_response(
                    lambda item: item.url.endswith("/auction-private-buy")
                ) as pending:
                    private_offer.locator("button").nth(1).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                private_trade = page.locator(
                    "#auction-attendees .private-trade-card"
                ).first
                private_trade.locator("summary").click()
                private_sell = private_trade.locator(".private-trade-sell")
                private_sell.locator("select").select_option("healing_pill")
                with page.expect_response(
                    lambda item: item.url.endswith(
                        "/auction-private-bargain"
                    )
                ) as pending:
                    private_sell.get_by_role("button", name="抬价").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                private_trade = page.locator(
                    "#auction-attendees .private-trade-card"
                ).first
                private_trade.locator("summary").click()
                private_sell = private_trade.locator(".private-trade-sell")
                private_sell.locator("select").select_option("healing_pill")
                with page.expect_response(
                    lambda item: item.url.endswith("/auction-private-sell")
                ) as pending:
                    private_sell.get_by_role(
                        "button", name="卖给对方"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()

                for _ in range(int(
                    engine.definitions.systems["auction_system"]["auction_rounds"]
                )):
                    with page.expect_response(
                        lambda item: item.url.endswith("/auction-advance")
                    ) as pending:
                        page.locator("#auction-advance-round").click()
                    assert pending.value.status == 200, pending.value.text()
                    page.locator("body:not(.busy)").wait_for()
                    if "散场黑市" in page.locator(
                        "#auction-title"
                    ).text_content():
                        break
                assert "散场黑市" in page.locator(
                    "#auction-title"
                ).text_content()
                page.locator("#black-market-pattern").fill("寒潭玄铁")
                with page.expect_response(
                    lambda item: item.url.endswith("/black-market-search")
                ) as pending:
                    page.locator(
                        "#black-market-search-form button[type=submit]"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                black_buy = page.locator(
                    "#black-market-results .auction-lot button:not([disabled])"
                ).first
                assert black_buy.count() == 1
                with page.expect_response(
                    lambda item: item.url.endswith("/black-market-buy")
                ) as pending:
                    black_buy.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                black_sell = page.locator(
                    "#black-market-sellables button"
                ).first
                assert black_sell.count() == 1
                with page.expect_response(
                    lambda item: item.url.endswith("/black-market-sell")
                ) as pending:
                    black_sell.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                with page.expect_response(
                    lambda item: item.url.endswith("/black-market-leave")
                ) as pending:
                    page.locator("#black-market-leave").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()

                if not page.locator("#map-card").evaluate(
                    "node => node.classList.contains('panel-open')"
                ):
                    page.locator('[data-panel-target="map"]').click(force=True)
                safe_travel = page.locator(
                    '.map-travel[data-travel-status="safe"]:not([disabled])'
                ).first
                assert safe_travel.count() == 1
                destination = safe_travel.get_attribute("data-destination")
                with page.expect_response(
                    lambda item: item.url.endswith("/map-travel")
                ) as pending:
                    safe_travel.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                for _ in range(10):
                    if page.evaluate("!game.pending_event"):
                        break
                    if page.locator("#map-card").evaluate(
                        "node => node.classList.contains('panel-open')"
                    ):
                        page.locator("#map-toggle").click(force=True)
                    choice = page.locator(
                        "#event-choices button:not([disabled])"
                    ).first
                    choice_context = page.evaluate(
                        "({eventId:game.pending_event.id, "
                        "choiceId:game.pending_event.choices.find(row => row.enabled).id})"
                    )
                    with page.expect_response(
                        lambda item: item.url.endswith("/choice")
                    ) as pending:
                        choice.click()
                    assert pending.value.status == 200, (
                        choice_context, pending.value.text()
                    )
                    page.locator("body:not(.busy)").wait_for()
                assert page.evaluate("game.map.current_location") == destination
                assert destination in page.locator(
                    "#player-subtitle"
                ).text_content() or page.evaluate(
                    "game.map.current_name"
                ) in page.locator("#player-subtitle").text_content()

                page.evaluate("id => loadGame(id)", game_id)
                page.locator("body:not(.busy)").wait_for()
                known = set(
                    engine.store.load(game_id).entities.with_component("core.identity")
                )
                engine.execute(
                    game_id,
                    RegisterCharacter(
                        "烟测敌手", 30, "male", "human", "supreme_wood", "dao",
                        "core", 1, "human",
                    ),
                )
                current = set(
                    engine.store.load(game_id).entities.with_component("core.identity")
                )
                enemy_id = (current - known).pop()
                response_data = page.evaluate(
                    """async ([gameId, enemyId]) => {
                        const response = await fetch(`/api/games/${gameId}/fight`, {
                          method:'POST', headers:{'Content-Type':'application/json'},
                          body:JSON.stringify({target_id:enemyId, objective:'duel'}),
                        });
                        const data = await response.json();
                        if (!response.ok) throw new Error(data.error || 'fight failed');
                        render(data);
                        return data;
                    }""",
                    [game_id, enemy_id],
                )
                assert isinstance(response_data["seed"], int)
                page.locator("#battle-report-card").wait_for(state="visible")
                battle_text = page.locator("#battle-report-card").inner_text()
                assert "烟测敌手" in battle_text
                assert "NaN" not in battle_text
                assert "undefined" not in battle_text
                assert "null" not in battle_text
                assert "未知" not in battle_text
                assert "天机数 null" not in page.locator("body").inner_text()
                page.locator("#battle-report-toggle").click()

                for index, (path, start_world) in enumerate((
                    ("dao", "human"), ("demonic", "human"),
                    ("ghost", "hell"), ("monster", "human"),
                    ("buddhist", "human"), ("confucian", "human"),
                ), 1):
                    route_game = engine.create_game(
                        f"浏览器路线{index}", seed=7000 + index,
                        path=path, start_world=start_world,
                        monster_species_id="serpent" if path == "monster" else None,
                    )
                    page.evaluate("id => loadGame(id)", route_game["id"])
                    page.locator("body:not(.busy)").wait_for()
                    body_text = page.locator("body").inner_text()
                    assert "NaN" not in body_text, path
                    assert "undefined" not in body_text, path
                    assert "天机数 null" not in body_text, path
                    assert f"天机数 {7000 + index}" in body_text, path
                    if path == "monster":
                        page.locator('[data-panel-target="bloodline"]').click(force=True)
                        bloodline_text = page.locator("#bloodline-card").text_content()
                        assert "蛇属" in bloodline_text, bloodline_text
                    assert_visible_panels_clean(page)

                def choose_story(choice_id: str) -> None:
                    choices = page.evaluate("game.pending_event.choices")
                    choice_index = next(
                        index for index, row in enumerate(choices)
                        if row["id"] == choice_id
                    )
                    button = page.locator(
                        "#event-choices button"
                    ).nth(choice_index)
                    assert button.is_enabled(), (choice_id, choices)
                    with page.expect_response(
                        lambda item: item.url.endswith("/choice")
                    ) as pending:
                        button.click()
                    assert pending.value.status == 200, pending.value.text()
                    page.locator("body:not(.busy)").wait_for()

                monster_flow = engine.create_game(
                    "妖族进化烟测", seed=7101, path="monster",
                    start_world="human", monster_species_id="serpent",
                )
                monster_flow_id = str(monster_flow["id"])
                monster_flow_actor = str(monster_flow["player"]["id"])
                monster_flow_state = engine.store.load(monster_flow_id)
                monster_flow_cultivation = monster_flow_state.entities.require(
                    monster_flow_actor, "cultivation.state"
                )
                mortal_realm = engine.definitions.realms[0]
                monster_flow_cultivation.update(
                    realm_id=mortal_realm.id,
                    layer=mortal_realm.layers,
                    opportunity=10**18,
                    bottleneck="major",
                )
                monster_flow_state.entities.put(
                    monster_flow_actor, "cultivation.state",
                    monster_flow_cultivation,
                )
                monster_flow_bloodline = monster_flow_state.entities.require(
                    monster_flow_actor, "dlc.monster.bloodline"
                )
                monster_flow_bloodline.update(
                    evolution_id="SERPENT_BASE",
                    evolution_history=["SERPENT_BASE"],
                )
                monster_flow_state.entities.put(
                    monster_flow_actor, "dlc.monster.bloodline",
                    monster_flow_bloodline,
                )
                engine.store.save(
                    monster_flow_state, [], player_name="妖族进化烟测",
                    expected_revision=monster_flow_state.revision,
                )
                page.evaluate("id => loadGame(id)", monster_flow_id)
                page.locator("body:not(.busy)").wait_for()
                if "panel-open" not in (
                    page.locator("#bloodline-card").get_attribute("class")
                    or ""
                ):
                    page.locator(
                        '[data-panel-target="bloodline"]'
                    ).click(force=True)
                normal_evolution = page.locator(
                    "#bloodline-candidates .bloodline-candidate"
                ).filter(has_text="灵蛇")
                with page.expect_response(
                    lambda item: item.url.endswith("/monster-evolve")
                ) as pending:
                    normal_evolution.get_by_role(
                        "button", name="选择进化"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.evaluate("game.player.realm_index") == 1
                page.locator("#bloodline-toggle").click()

                crossing_game = engine.create_game(
                    "偷渡灵界烟测", seed=243, path="dao"
                )
                crossing_id = str(crossing_game["id"])
                crossing_actor = str(crossing_game["player"]["id"])
                crossing_state = engine.store.load(crossing_id)
                crossing_cultivation = crossing_state.entities.require(
                    crossing_actor, "cultivation.state"
                )
                crossing_cultivation.update(
                    realm_id="spirit", layer=1, bottleneck=None
                )
                crossing_state.entities.put(
                    crossing_actor, "cultivation.state", crossing_cultivation
                )
                engine.store.save(
                    crossing_state, [], player_name="偷渡灵界烟测",
                    expected_revision=crossing_state.revision,
                )
                for item_id in ("spirit_node_info", "broken_god"):
                    engine.execute(
                        crossing_id,
                        GrantItem(
                            crossing_actor, item_id, 1, "browser-smoke"
                        ),
                    )
                page.evaluate("id => loadGame(id)", crossing_id)
                page.locator("body:not(.busy)").wait_for()
                assert page.locator("#spirit-crossing-action").is_visible()
                with page.expect_response(
                    lambda item: item.url.endswith("/spirit-crossing")
                ) as pending:
                    page.locator("#spirit-crossing-action").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                for choice_id in ("locate", "endure", "break_boundary"):
                    choose_story(choice_id)
                assert page.evaluate("game.player.world") == "spirit"

                celestial_flow = engine.create_game(
                    "仙界飞升烟测", seed=99117, path="dao",
                    start_world="spirit",
                )
                celestial_flow_id = str(celestial_flow["id"])
                celestial_flow_actor = str(celestial_flow["player"]["id"])
                celestial_flow_state = engine.store.load(celestial_flow_id)
                celestial_flow_cultivation = (
                    celestial_flow_state.entities.require(
                        celestial_flow_actor, "cultivation.state"
                    )
                )
                celestial_flow_cultivation.update(
                    realm_id="mahayana", layer=9, path="dao",
                    opportunity=10_000_000.0, bottleneck="major",
                    heart_demon=0.0,
                )
                celestial_flow_state.entities.put(
                    celestial_flow_actor, "cultivation.state",
                    celestial_flow_cultivation,
                )
                engine.store.save(
                    celestial_flow_state, [], player_name="仙界飞升烟测",
                    expected_revision=celestial_flow_state.revision,
                )
                page.evaluate("id => loadGame(id)", celestial_flow_id)
                page.locator("body:not(.busy)").wait_for()
                assert page.locator("#spirit-crossing-action").is_visible()
                assert page.locator(
                    "#spirit-crossing-action"
                ).get_attribute("data-operation") == "celestial-ascension"
                with page.expect_response(
                    lambda item: item.url.endswith("/celestial-ascension")
                ) as pending:
                    page.locator("#spirit-crossing-action").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                for choice_id in (
                    "endure", "cross", "receive", "sever", "destroy",
                    "receive", "anchor", "answer", "ascend",
                ):
                    choose_story(choice_id)
                assert page.evaluate("game.player.world") == "celestial"

                asura_flow = engine.create_game(
                    "修罗飞升烟测", seed=99117, path="demonic",
                    start_world="demon",
                )
                asura_flow_id = str(asura_flow["id"])
                asura_flow_actor = str(asura_flow["player"]["id"])
                asura_flow_state = engine.store.load(asura_flow_id)
                asura_flow_cultivation = asura_flow_state.entities.require(
                    asura_flow_actor, "cultivation.state"
                )
                asura_flow_cultivation.update(
                    realm_id="mahayana", layer=9, path="demonic",
                    opportunity=10_000_000.0, bottleneck="major",
                    heart_demon=0.0,
                )
                asura_flow_cultivation["qi_experience"]["demon"] = (
                    25.0 * 30 * 30
                )
                asura_flow_state.entities.put(
                    asura_flow_actor, "cultivation.state",
                    asura_flow_cultivation,
                )
                asura_location = asura_flow_state.entities.require(
                    asura_flow_actor, "world.location"
                )
                asura_location.update(
                    world_id="true_demon",
                    location_id=engine.definitions.default_location(
                        "true_demon"
                    ),
                )
                asura_flow_state.entities.put(
                    asura_flow_actor, "world.location", asura_location
                )
                asura_story = asura_flow_state.entities.require(
                    asura_flow_actor, "story.state"
                )
                asura_story["attributes"].update(karma=0.0, sha_qi=80.0)
                asura_flow_state.entities.put(
                    asura_flow_actor, "story.state", asura_story
                )
                engine.store.save(
                    asura_flow_state, [], player_name="修罗飞升烟测",
                    expected_revision=asura_flow_state.revision,
                )
                page.evaluate("id => loadGame(id)", asura_flow_id)
                page.locator("body:not(.busy)").wait_for()
                assert page.locator("#spirit-crossing-action").is_visible()
                assert page.locator(
                    "#spirit-crossing-action"
                ).get_attribute("data-operation") == "asura-ascension"
                with page.expect_response(
                    lambda item: item.url.endswith("/asura-ascension")
                ) as pending:
                    page.locator("#spirit-crossing-action").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                for choice_id in (
                    "endure", "cross", "receive", "master", "devour",
                    "receive", "command", "answer", "ascend",
                ):
                    choose_story(choice_id)
                assert page.evaluate("game.player.world") == "asura"

                field_game = engine.create_game(
                    "灵田界面烟测", seed=8799, preset_id="core"
                )
                field_id = str(field_game["id"])
                field_actor = str(field_game["player"]["id"])
                engine.execute(
                    field_id,
                    GrantItem(
                        field_actor, "dew_grass_seed", 2, "browser-smoke"
                    ),
                )
                page.evaluate("id => loadGame(id)", field_id)
                page.locator("body:not(.busy)").wait_for()
                page.locator(
                    '[data-panel-target="spirit-field"]'
                ).click(force=True)
                with page.expect_response(
                    lambda item: item.url.endswith("/spirit-field-reclaim")
                ) as pending:
                    page.get_by_role("button", name="开垦此顷").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                empty_plot = page.locator(
                    "#spirit-field-plots .spirit-crop-tile"
                ).filter(has_text="空闲沃土").first
                empty_plot.locator("select").select_option("dew_grass")
                with page.expect_response(
                    lambda item: item.url.endswith("/spirit-field-plant")
                ) as pending:
                    empty_plot.get_by_role("button", name="播种").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                crop = page.locator(
                    "#spirit-field-plots .spirit-crop-tile"
                ).filter(has_text="凝露草").first
                with page.expect_response(
                    lambda item: item.url.endswith("/spirit-field-irrigate")
                ) as pending:
                    crop.get_by_role("button", name="灌溉催熟").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                crop = page.locator(
                    "#spirit-field-plots .spirit-crop-tile"
                ).filter(has_text="凝露草").first
                with page.expect_response(
                    lambda item: item.url.endswith("/spirit-field-harvest")
                ) as pending:
                    crop.get_by_role("button", name="采收").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                page.locator('[data-panel-target="market"]').click(force=True)
                plant_sale = page.locator("#market-plant-sellables button").first
                assert plant_sale.count() == 1
                with page.expect_response(
                    lambda item: item.url.endswith("/market-sell-plant")
                ) as pending:
                    plant_sale.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.locator("#market-plant-sellables button").count() == 0
                page.locator("#market-toggle").click()
                if not page.locator("#spirit-field-card").evaluate(
                    "node => node.classList.contains('panel-open')"
                ):
                    page.locator(
                        '[data-panel-target="spirit-field"]'
                    ).click(force=True)
                empty_plot = page.locator(
                    "#spirit-field-plots .spirit-crop-tile"
                ).filter(has_text="空闲沃土").first
                empty_plot.locator("select").select_option("dew_grass")
                with page.expect_response(
                    lambda item: item.url.endswith("/spirit-field-plant")
                ) as pending:
                    empty_plot.get_by_role("button", name="播种").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                crop = page.locator(
                    "#spirit-field-plots .spirit-crop-tile"
                ).filter(has_text="凝露草").first
                with page.expect_response(
                    lambda item: item.url.endswith("/spirit-field-irrigate")
                ) as pending:
                    crop.get_by_role("button", name="灌溉催熟").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                crop = page.locator(
                    "#spirit-field-plots .spirit-crop-tile"
                ).filter(has_text="凝露草").first
                with page.expect_response(
                    lambda item: item.url.endswith("/spirit-field-harvest")
                ) as pending:
                    crop.get_by_role("button", name="采收").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                page.locator(
                    "details.alchemy-workbench > summary"
                ).click()
                page.locator("#alchemy-target").select_option("healing_pill")
                page.locator("#alchemy-materials input").first.fill("1")
                with page.expect_response(
                    lambda item: item.url.endswith("/alchemy")
                ) as pending:
                    page.locator("#alchemy-refine").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.locator("#alchemy-materials input").count() == 0

                controls = engine.create_game(
                    "核心按钮烟测", seed=112233, preset_id="core"
                )
                controls_id = str(controls["id"])
                controls_actor = str(controls["player"]["id"])
                for technique_id in (
                    "TECH_BODY_MORTAL", "TECH_SPIRIT_SENSE"
                ):
                    engine.execute(
                        controls_id,
                        GrantTechnique(controls_actor, technique_id),
                    )
                for item_id, quantity in (
                    ("healing_pill", 1),
                    ("spirit_stone", 1000),
                    ("spirit_sword", 1),
                ):
                    engine.execute(
                        controls_id,
                        GrantItem(
                            controls_actor, item_id, quantity, "browser-smoke"
                        ),
                    )
                page.evaluate("id => loadGame(id)", controls_id)
                page.locator("body:not(.busy)").wait_for()
                page.locator(
                    "details.technique-library > summary"
                ).click()
                body_name = engine.definitions.techniques[
                    "TECH_BODY_MORTAL"
                ].name
                body_manual = page.locator(
                    "#known-technique-list .known-technique"
                ).filter(has_text=body_name)
                with page.expect_response(
                    lambda item: item.url.endswith("/equip-technique")
                ) as pending:
                    body_manual.get_by_role(
                        "button", name="体", exact=True
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                sense_name = engine.definitions.techniques[
                    "TECH_SPIRIT_SENSE"
                ].name
                sense_manual = page.locator(
                    "#known-technique-list .known-technique"
                ).filter(has_text=sense_name)
                with page.expect_response(
                    lambda item: item.url.endswith("/equip-technique")
                ) as pending:
                    sense_manual.get_by_role(
                        "button", name="识", exact=True
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert body_name in page.locator(
                    "#technique-list"
                ).text_content()
                assert sense_name in page.locator(
                    "#technique-list"
                ).text_content()

                controls_state = engine.store.load(controls_id)
                controls_cultivation = controls_state.entities.require(
                    controls_actor, "cultivation.state"
                )
                controls_cultivation.update(
                    opportunity=1_000_000.0, bottleneck="minor"
                )
                controls_state.entities.put(
                    controls_actor, "cultivation.state", controls_cultivation
                )
                controls_body = controls_state.entities.require(
                    controls_actor, "cultivation.body"
                )
                controls_body.update(progress=70.0, ready=True)
                controls_state.entities.put(
                    controls_actor, "cultivation.body", controls_body
                )
                controls_sense = controls_state.entities.require(
                    controls_actor, "cultivation.divine_sense"
                )
                controls_sense["experience"] = 1_000_000_000.0
                controls_state.entities.put(
                    controls_actor,
                    "cultivation.divine_sense",
                    controls_sense,
                )
                controls_condition = controls_state.entities.require(
                    controls_actor, "combat.condition"
                )
                controls_condition["hp_ratio"] = 0.5
                controls_state.entities.put(
                    controls_actor, "combat.condition", controls_condition
                )
                controls_ledger = controls_state.entities.require(
                    controls_actor, "economy.asset_ledger"
                )
                controls_instances = dict(controls_ledger["instances"])
                controls_sequence = int(controls_ledger["next_sequence"])
                special_asset_id = (
                    f"asset:{controls_actor}:{controls_sequence}"
                )
                special_plant = engine.definitions.systems[
                    "spirit_field"
                ]["plants"]["mystic_heaven_vine"]
                controls_instances[special_asset_id] = {
                    "id": special_asset_id,
                    "kind": "harvested_spirit_plant",
                    "definition_id": "mystic_heaven_vine",
                    "name": special_plant["name"],
                    "created_year": controls_state.clock.year,
                    "metadata": {
                        "plant_id": "mystic_heaven_vine",
                        "plant_kind": special_plant["kind"],
                        "years": special_plant["use_years"],
                        "quality": 1.0,
                    },
                    "reservation_id": None,
                }
                controls_ledger.update(
                    next_sequence=controls_sequence + 1,
                    instances=controls_instances,
                )
                controls_state.entities.put(
                    controls_actor,
                    "economy.asset_ledger",
                    controls_ledger,
                )
                engine.store.save(
                    controls_state, [], player_name="核心按钮烟测",
                    expected_revision=controls_state.revision,
                )
                page.evaluate("id => loadGame(id)", controls_id)
                page.locator("body:not(.busy)").wait_for()
                page.locator('[data-panel-target="inventory"]').click(force=True)
                healing = page.locator("#inventory-list .item").filter(
                    has_text=engine.definitions.items["healing_pill"].name
                )
                with page.expect_response(
                    lambda item: item.url.endswith("/use-item")
                ) as pending:
                    healing.get_by_role("button", name="服用").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                special_row = page.locator("#inventory-list .item").filter(
                    has_text=special_plant["name"]
                )
                with page.expect_response(
                    lambda item: item.url.endswith("/spirit-plant-use")
                ) as pending:
                    special_row.get_by_role("button", name="使用").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.locator("#inventory-list .item").filter(
                    has_text=special_plant["name"]
                ).get_by_role("button", name="使用").count() == 0
                page.locator("#inventory-toggle").click()
                with page.expect_response(
                    lambda item: item.url.endswith("/breakthrough")
                ) as pending:
                    page.locator("#breakthrough-action").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                with page.expect_response(
                    lambda item: item.url.endswith("/body-breakthrough")
                ) as pending:
                    page.locator("#body-breakthrough-action").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                with page.expect_response(
                    lambda item: item.url.endswith("/sense-breakthrough")
                ) as pending:
                    page.locator("#sense-breakthrough-action").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                page.locator('[data-panel-target="captive"]').click(force=True)
                with page.expect_response(
                    lambda item: item.url.endswith("/craft-puppet")
                ) as pending:
                    page.locator("#craft-puppet").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert "机关傀儡" in page.locator(
                    "#puppet-list"
                ).text_content()
                page.locator('[data-panel-target="settings"]').click(force=True)
                with page.expect_response(
                    lambda item: item.url.endswith("/settings")
                ) as pending:
                    page.locator("#setting-combat-popup").check()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.locator("#setting-combat-popup").is_checked()

                social = engine.create_game(
                    "关系界面烟测", seed=4202, preset_id="core"
                )
                social_id = str(social["id"])
                social_actor = str(social["player"]["id"])

                def register_social(name: str, gender: str) -> str:
                    before = set(
                        engine.store.load(social_id).entities.with_component(
                            "core.identity"
                        )
                    )
                    engine.execute(
                        social_id,
                        RegisterCharacter(
                            name, 260, gender, "human", "supreme_metal", "dao",
                            "core", 1, "human", 500,
                        ),
                    )
                    after = set(
                        engine.store.load(social_id).entities.with_component(
                            "core.identity"
                        )
                    )
                    return (after - before).pop()

                companion_id = register_social("照月", "female")
                friend_id = register_social("青简", "male")
                concubine_id = register_social("绛珠", "female")
                engine.execute(
                    social_id,
                    FormRelationship(
                        social_actor, companion_id, "dao_companion",
                        {"last_interactions": {}},
                    ),
                )
                engine.execute(
                    social_id,
                    FormRelationship(social_actor, friend_id, "friend"),
                )
                engine.execute(
                    social_id,
                    FormRelationship(social_actor, concubine_id, "friend"),
                )
                engine.change_affinity(social_id, companion_id, 60)
                engine.change_affinity(social_id, friend_id, 60)
                engine.change_affinity(social_id, concubine_id, 60)
                social_state = engine.store.load(social_id)
                social_cultivation = social_state.entities.require(
                    social_actor, "cultivation.state"
                )
                social_cultivation.update(realm_id="nascent", layer=1)
                social_state.entities.put(
                    social_actor, "cultivation.state", social_cultivation
                )
                engine.store.save(
                    social_state, [], player_name="关系界面烟测",
                    expected_revision=social_state.revision,
                )
                page.evaluate("id => loadGame(id)", social_id)
                page.locator("body:not(.busy)").wait_for()
                page.locator('[data-panel-target="faction"]').click(force=True)
                creation = page.locator("#faction-summary form")
                creation.locator("input").fill("烟测宗")
                with page.expect_response(
                    lambda item: item.url.endswith("/create-faction")
                ) as pending:
                    creation.get_by_role("button", name="开宗立派").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.locator("#faction-title").text_content() == "烟测宗"
                social_faction_id = str(
                    engine.get_game(social_id)["faction"]["id"]
                )
                succession = page.get_by_role(
                    "button", name="安排后事并指定继任者"
                )
                assert succession.count() == 1
                with page.expect_response(
                    lambda item: item.url.endswith("/faction-succession")
                ) as pending:
                    succession.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                page.locator(
                    '[data-panel-target="relationship"]'
                ).click(force=True)
                companion_row = page.locator(
                    "#dao-companion-list .companion-row"
                ).filter(has_text="照月")
                assert "结丹初期·1层" in companion_row.text_content()
                with page.expect_response(
                    lambda item: item.url.endswith("/party")
                ) as pending:
                    companion_row.get_by_role(
                        "button", name="邀请同行"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert "照月" in page.locator("#party-list").text_content()
                companion_row = page.locator(
                    "#dao-companion-list .companion-row"
                ).filter(has_text="照月")
                with page.expect_response(
                    lambda item: item.url.endswith("/dao-companion")
                ) as pending:
                    companion_row.get_by_role(
                        "button", name="亲密交谈"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                companion_row = page.locator(
                    "#dao-companion-list .companion-row"
                ).filter(has_text="照月")
                faction_invite = companion_row.get_by_role(
                    "button", name="引荐入宗"
                )
                assert faction_invite.count() == 1
                with page.expect_response(
                    lambda item: item.url.endswith("/relationship-faction")
                ) as pending:
                    faction_invite.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                friend_row = page.locator(
                    "#dao-friend-list .friend-row"
                ).filter(has_text="青简")
                with page.expect_response(
                    lambda item: item.url.endswith("/dao-friend")
                ) as pending:
                    friend_row.get_by_role(
                        "button", name="交流心得"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                friend_row = page.locator(
                    "#dao-friend-list .friend-row"
                ).filter(has_text="青简")
                guest_invite = friend_row.get_by_role(
                    "button", name="邀请客卿"
                )
                assert guest_invite.count() == 1
                with page.expect_response(
                    lambda item: item.url.endswith("/intrigue-guest")
                ) as pending:
                    guest_invite.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                page.locator('[data-panel-target="intrigue"]').click(force=True)
                intrigue_text = page.locator("#intrigue-card").text_content()
                assert "青简" in intrigue_text
                assert "undefined" not in intrigue_text
                assert "NaN" not in intrigue_text
                page.locator(
                    '[data-panel-target="relationship"]'
                ).click(force=True)
                with page.expect_response(
                    lambda item: item.url.endswith("/relationship-exit")
                ) as pending:
                    page.locator(
                        "#dao-friend-list .friend-row"
                    ).filter(has_text="青简").get_by_role(
                        "button", name="解除道友"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert "青简" not in page.locator(
                    "#dao-friend-list"
                ).text_content()

                concubine_friend = page.locator(
                    "#dao-friend-list .friend-row"
                ).filter(has_text="绛珠")
                recruit = concubine_friend.get_by_role(
                    "button", name="纳为侍妾"
                )
                assert recruit.count() == 1
                with page.expect_response(
                    lambda item: item.url.endswith("/concubine-action")
                ) as pending:
                    recruit.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                concubine_row = page.locator(
                    "#concubine-list .concubine-row"
                ).filter(has_text="绛珠")
                assert concubine_row.count() == 1
                concubine_text = concubine_row.text_content()
                assert "结丹" in concubine_text, repr(concubine_text)
                assert "寿元" in concubine_text
                assert "战力" in concubine_text
                assert "绛珠" not in page.locator(
                    "#dao-companion-list"
                ).text_content()
                assert "绛珠" not in page.locator(
                    "#dao-friend-list"
                ).text_content()
                with page.expect_response(
                    lambda item: item.url.endswith("/concubine-action")
                ) as pending:
                    concubine_row.get_by_role(
                        "button", name="当作炉鼎"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                concubine_row = page.locator(
                    "#concubine-list .concubine-row"
                ).filter(has_text="绛珠")
                assert concubine_row.get_by_role(
                    "button", name="本期已用"
                ).is_disabled()
                with page.expect_response(
                    lambda item: item.url.endswith("/concubine-action")
                ) as pending:
                    concubine_row.get_by_role(
                        "button", name="遣散"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert "绛珠" not in page.locator(
                    "#concubine-list"
                ).text_content()

                intrigue_state = engine.store.load(social_id)
                companion_cultivation = intrigue_state.entities.require(
                    companion_id, "cultivation.state"
                )
                companion_cultivation.update(
                    realm_id="foundation", layer=1
                )
                intrigue_state.entities.put(
                    companion_id, "cultivation.state",
                    companion_cultivation,
                )
                engine.store.save(
                    intrigue_state, [], player_name="关系界面烟测",
                    expected_revision=intrigue_state.revision,
                )
                page.evaluate("id => loadGame(id)", social_id)
                page.locator("body:not(.busy)").wait_for()
                page.locator(
                    '[data-panel-target="intrigue"]'
                ).click(force=True)
                intrigue_section = page.locator(
                    "#intrigue-content .intrigue-sect"
                )
                member_details = intrigue_section.locator(
                    ".intrigue-details"
                ).first
                member_details.locator("summary").click()
                companion_member = member_details.locator(
                    ".intrigue-member"
                ).filter(has_text="照月")
                assert companion_member.count() == 1
                with page.expect_response(
                    lambda item: item.url.endswith("/intrigue-personnel")
                ) as pending:
                    companion_member.get_by_role(
                        "button", name="赏", exact=True
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                recruitment = page.locator(
                    "#intrigue-content .intrigue-sect "
                    ".intrigue-recruitment"
                )
                with page.expect_response(
                    lambda item: item.url.endswith(
                        "/intrigue-recruitment"
                    )
                ) as pending:
                    recruitment.get_by_role(
                        "button", name="提交扩招决议"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                recruitment = page.locator(
                    "#intrigue-content .intrigue-sect "
                    ".intrigue-recruitment"
                )
                candidates = recruitment.locator(
                    ".intrigue-recruitment-candidate input"
                )
                if candidates.count():
                    candidates.first.check()
                selected_candidates = candidates.evaluate_all(
                    "nodes => nodes.filter(node => node.checked)"
                    ".map(node => node.value)"
                )
                recruitment_state = engine.store.load(social_id)
                recruitment_governance = recruitment_state.entities.require(
                    social_faction_id, "dlc.intrigue.governance"
                )
                backend_candidates = list(
                    recruitment_governance["pending_recruitment"][
                        "candidate_ids"
                    ]
                )
                assert set(selected_candidates) <= set(backend_candidates)
                with page.expect_request(
                    lambda item: item.url.endswith(
                        "/intrigue-recruitment"
                    )
                ) as sent, page.expect_response(
                    lambda item: item.url.endswith(
                        "/intrigue-recruitment"
                    )
                ) as pending:
                    recruitment.get_by_role(
                        "button", name=(
                            "录取所选弟子"
                            if candidates.count()
                            else "结束本次招募"
                        ),
                    ).click()
                assert pending.value.status == 200, (
                    pending.value.text().encode("unicode_escape"),
                    sent.value.post_data_json,
                    backend_candidates,
                )
                page.locator("body:not(.busy)").wait_for()
                resolution = page.locator(
                    "#intrigue-content .intrigue-sect "
                    ".intrigue-resolution-form"
                )
                resolution.locator("select").first.select_option(
                    "investment"
                )
                with page.expect_response(
                    lambda item: item.url.endswith("/intrigue-resolution")
                ) as pending:
                    resolution.get_by_role(
                        "button", name="提交议事"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert "重大资源投资" in page.locator(
                    "#intrigue-content .intrigue-resolution-log"
                ).text_content()

                page.locator('[data-panel-target="faction"]').click(force=True)
                engine.execute(
                    social_id,
                    ChangeContribution(
                        social_actor, social_faction_id, 100, "browser-smoke"
                    ),
                )
                page.evaluate("id => loadGame(id)", social_id)
                page.locator("body:not(.busy)").wait_for()
                faction_text = page.locator("#faction-card").text_content()
                assert "undefined" not in faction_text
                assert "NaN" not in faction_text
                reward = page.locator(
                    "#faction-reward-options .reward-choice"
                ).first
                assert reward.is_enabled()
                with page.expect_response(
                    lambda item: item.url.endswith("/faction-reward")
                ) as pending:
                    reward.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                dispatch = page.locator('[data-dispatch="item"]')
                assert dispatch.is_enabled()
                with page.expect_response(
                    lambda item: item.url.endswith("/faction-dispatch")
                ) as pending:
                    dispatch.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                faction_mentorship = page.locator(
                    "#faction-roster-list"
                ).get_by_role("button", name="收徒").first
                assert faction_mentorship.count() == 1
                with page.expect_response(
                    lambda item: item.url.endswith("/faction-relationship")
                ) as pending:
                    faction_mentorship.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                diplomacy = page.locator(
                    "#faction-summary .diplomacy-form"
                )
                assert diplomacy.count() == 1
                diplomacy.locator("select").nth(1).select_option("war")
                with page.expect_response(
                    lambda item: item.url.endswith("/faction-diplomacy")
                ) as pending:
                    diplomacy.get_by_role(
                        "button", name="提交表决"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                page.locator('[data-panel-target="war"]').click(force=True)
                war_card = page.locator("#war-list .war-card.active").first
                assert war_card.count() == 1
                war_text = war_card.text_content()
                assert "总战力" in war_text
                assert "境界未明" not in war_text
                assert "势力未明" not in war_text
                assert "NaN" not in war_text
                with page.expect_response(
                    lambda item: item.url.endswith("/war-action")
                ) as pending:
                    war_card.get_by_role(
                        "button", name="跳过先锋，命主力会战"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                war_card = page.locator("#war-list .war-card.active").first
                assert war_card.get_by_role(
                    "button", name="亲自参加第 2 场会战"
                ).count() == 1
                with page.expect_response(
                    lambda item: item.url.endswith("/war-action")
                ) as pending:
                    war_card.get_by_role(
                        "button", name="命主力会战（本人不参战）"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                war_card = page.locator(
                    "#war-list .war-card:not(.ended)"
                ).first
                peace = war_card.locator(".war-peace-form")
                peace.locator("select").first.select_option("white_peace")
                with page.expect_response(
                    lambda item: item.url.endswith("/war-peace")
                ) as pending:
                    peace.get_by_role(
                        "button", name="以战果提出条件"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.locator(
                    "#war-list .war-card.ended"
                ).count() == 1
                page.locator('[data-panel-target="family"]').click(force=True)
                bounty_form = page.locator(
                    "#family-content .governance-form"
                )
                assert bounty_form.count() == 1
                with page.expect_response(
                    lambda item: item.url.endswith("/issue-bounty")
                ) as pending:
                    bounty_form.get_by_role(
                        "button", name="颁布通缉"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert "追缉中" in page.locator(
                    "#family-content"
                ).text_content()
                page.locator('[data-panel-target="faction"]').click(force=True)
                with page.expect_response(
                    lambda item: item.url.endswith("/leave-faction")
                ) as pending:
                    page.locator("#faction-summary").get_by_role(
                        "button", name="退出宗门"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert "尚未入门" in page.locator(
                    "#faction-role"
                ).text_content()

                status_game = engine.create_game(
                    "侍妾处境烟测", seed=2205, gender="female"
                )
                status_id = str(status_game["id"])
                status_actor = str(status_game["player"]["id"])
                before = set(
                    engine.store.load(status_id).entities.with_component(
                        "core.identity"
                    )
                )
                engine.execute(
                    status_id,
                    RegisterCharacter(
                        "禁府之主", 180, "male", "human",
                        "supreme_fire", "dao", "core", 2, "human",
                    ),
                )
                after = set(
                    engine.store.load(status_id).entities.with_component(
                        "core.identity"
                    )
                )
                status_owner = (after - before).pop()
                engine.execute(
                    status_id,
                    EnterConcubineStatus(status_actor, status_owner),
                )
                page.evaluate("id => loadGame(id)", status_id)
                page.locator("body:not(.busy)").wait_for()
                page.locator(
                    '[data-panel-target="relationship"]'
                ).click(force=True)
                assert "禁府之主" in page.locator(
                    "#concubine-status"
                ).text_content()
                with page.expect_response(
                    lambda item: item.url.endswith("/concubine-status")
                ) as pending:
                    page.locator("#concubine-status").get_by_role(
                        "button", name="主动依附"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                with page.expect_response(
                    lambda item: item.url.endswith("/concubine-status")
                ) as pending:
                    page.locator("#concubine-status").get_by_role(
                        "button", name="索要灵石"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                with page.expect_response(
                    lambda item: item.url.endswith("/concubine-status")
                ) as pending:
                    page.locator("#concubine-status").get_by_role(
                        "button", name="谋求脱身"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert "禁府之主" in page.locator(
                    "#event-card"
                ).text_content()

                prison_game = engine.create_game("牢狱界面烟测", seed=7001)
                prison_id = str(prison_game["id"])
                prison_actor = str(prison_game["player"]["id"])
                before = set(
                    engine.store.load(prison_id).entities.with_component(
                        "core.identity"
                    )
                )
                engine.execute(
                    prison_id,
                    RegisterCharacter(
                        "边狱狱卒", 50, "male", "human", "supreme_earth",
                        "dao", "foundation", 1, "human",
                    ),
                )
                after = set(
                    engine.store.load(prison_id).entities.with_component(
                        "core.identity"
                    )
                )
                prison_owner = (after - before).pop()
                engine.execute(
                    prison_id,
                    EnterImprisonment(
                        prison_actor, prison_owner, 2,
                        "刑堂", "faction_prison", 30.0,
                    ),
                )
                page.evaluate("id => loadGame(id)", prison_id)
                page.locator("body:not(.busy)").wait_for()
                assert page.locator("#prison-card").is_visible()
                assert "尚余刑期 2 年" in page.locator(
                    "#prison-description"
                ).text_content()
                with page.expect_response(
                    lambda item: item.url.endswith("/prison-action")
                ) as pending:
                    page.locator("#prison-cultivate").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert "尚余刑期 1 年" in page.locator(
                    "#prison-description"
                ).text_content()

                mentor_game = engine.create_game(
                    "师徒界面烟测", seed=7301, preset_id="core"
                )
                mentor_id = str(mentor_game["id"])
                mentor_actor = str(mentor_game["player"]["id"])

                def register_mentor_person(
                    name: str, realm_id: str, layer: int
                ) -> str:
                    prior = set(
                        engine.store.load(mentor_id).entities.with_component(
                            "core.identity"
                        )
                    )
                    engine.execute(
                        mentor_id,
                        RegisterCharacter(
                            name, 80, "male", "human", "supreme_wood",
                            "dao", realm_id, layer, "human",
                        ),
                    )
                    current = set(
                        engine.store.load(mentor_id).entities.with_component(
                            "core.identity"
                        )
                    )
                    return (current - prior).pop()

                master_id = register_mentor_person("玄衡真人", "nascent", 1)
                disciple_id = register_mentor_person("小砚", "qi", 2)
                requester_id = register_mentor_person("问道童子", "mortal", 1)
                mentor_state = engine.store.load(mentor_id)
                mentor_state.relations.add(
                    source_id=master_id,
                    target_id=mentor_actor,
                    kind="master_disciple",
                    created_year=mentor_state.clock.year,
                    metadata={"last_requests": {}},
                )
                engine.store.save(
                    mentor_state, [], player_name="师徒界面烟测",
                    expected_revision=mentor_state.revision,
                )
                engine.execute(
                    mentor_id,
                    FormRelationship(
                        mentor_actor, disciple_id, "master_disciple"
                    ),
                )
                engine.offer_disciple_request(mentor_id, requester_id)
                engine.execute(
                    mentor_id,
                    GrantItem(
                        mentor_actor, "spirit_stone", 20, "browser-smoke"
                    ),
                )
                page.evaluate("id => loadGame(id)", mentor_id)
                page.locator("body:not(.busy)").wait_for()
                if "panel-open" not in (
                    page.locator("#relationship-card").get_attribute("class") or ""
                ):
                    page.locator(
                        '[data-panel-target="relationship"]'
                    ).click(force=True)
                master_row = page.locator(
                    "#relationship-list .relationship-row"
                ).filter(has_text="师父 · 玄衡真人")
                with page.expect_response(
                    lambda item: item.url.endswith("/master-request")
                ) as pending:
                    master_row.get_by_role(
                        "button", name="索要物品"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                disciple_row = page.locator(
                    "#relationship-list .relationship-row"
                ).filter(has_text="弟子 · 小砚")
                with page.expect_response(
                    lambda item: item.url.endswith("/disciple-gift")
                ) as pending:
                    disciple_row.get_by_role("button", name="赠物").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                request_row = page.locator(
                    "#relationship-list .pending-request"
                ).filter(has_text="问道童子")
                with page.expect_response(
                    lambda item: item.url.endswith("/disciple-request")
                ) as pending:
                    request_row.get_by_role(
                        "button", name="收入门下"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert "弟子 · 问道童子" in page.locator(
                    "#relationship-list"
                ).text_content()

                family_game = engine.create_game(
                    "立族界面烟测", seed=7401, preset_id="core"
                )
                family_id = str(family_game["id"])
                family_actor = str(family_game["player"]["id"])
                family_known = set(
                    engine.store.load(family_id).entities.with_component(
                        "core.identity"
                    )
                )
                engine.execute(
                    family_id,
                    RegisterCharacter(
                        "烟测后裔", 18, "female", "human", "supreme_wood",
                        "dao", "qi", 1, "human", 110,
                    ),
                )
                family_state = engine.store.load(family_id)
                family_child = next(iter(
                    set(family_state.entities.with_component("core.identity"))
                    - family_known
                ))
                lineage = family_state.entities.require(
                    family_actor, "family.lineage"
                )
                lineage["child_ids"] = [family_child]
                family_state.entities.put(
                    family_actor, "family.lineage", lineage
                )
                family_state.relations.add(
                    source_id=family_actor,
                    target_id=family_child,
                    kind="parent_child",
                    created_year=family_state.clock.year,
                )
                engine.store.save(
                    family_state, [], player_name="立族界面烟测",
                    expected_revision=family_state.revision,
                )
                page.evaluate("id => loadGame(id)", family_id)
                page.locator("body:not(.busy)").wait_for()
                page.locator('[data-panel-target="family"]').click(force=True)
                creation = page.locator(
                    "#family-content .governance-form"
                ).filter(has_text="建立修仙家族")
                creation.locator("input").fill("烟测世家")
                with page.expect_response(
                    lambda item: item.url.endswith("/create-family")
                ) as pending:
                    creation.get_by_role(
                        "button", name="开枝立族"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.locator("#family-title").text_content() == "烟测世家"
                assert "烟测后裔" in page.locator(
                    "#family-content"
                ).text_content()

                intercept_game = engine.create_game(
                    "同门截杀界面烟测", seed=7402
                )
                intercept_id = str(intercept_game["id"])
                intercept_actor = str(intercept_game["player"]["id"])
                intercept_faction = next(
                    row["id"] for row in intercept_game["available_factions"]
                    if row["external_id"] == "tianjian"
                )
                joined = engine.join_faction(
                    intercept_id, intercept_faction
                ).game
                intercept_target = min(
                    (
                        row for row in joined["faction"]["roster"]
                        if row["id"] != intercept_actor
                    ),
                    key=lambda row: (row["realm_index"], row["layer"]),
                )["id"]
                intercept_state = engine.store.load(intercept_id)
                actor_cultivation = intercept_state.entities.require(
                    intercept_actor, "cultivation.state"
                )
                actor_cultivation.update(realm_id="nascent", layer=9)
                intercept_state.entities.put(
                    intercept_actor, "cultivation.state", actor_cultivation
                )
                target_cultivation = intercept_state.entities.require(
                    intercept_target, "cultivation.state"
                )
                target_cultivation.update(realm_id="qi", layer=1)
                intercept_state.entities.put(
                    intercept_target, "cultivation.state", target_cultivation
                )
                engine.store.save(
                    intercept_state, [], player_name="同门截杀界面烟测",
                    expected_revision=intercept_state.revision,
                )
                page.evaluate("id => loadGame(id)", intercept_id)
                page.locator("body:not(.busy)").wait_for()
                page.locator('[data-panel-target="faction"]').click(force=True)
                target_row = page.locator(
                    "#faction-roster-list .roster-row"
                ).filter(has=page.locator(
                    f'[data-entity-id="{intercept_target}"]'
                ))
                if target_row.count() == 0:
                    target_name = next(
                        row["name"] for row in joined["faction"]["roster"]
                        if row["id"] == intercept_target
                    )
                    target_row = page.locator(
                        "#faction-roster-list .roster-row"
                    ).filter(has_text=target_name)
                assert target_row.count() == 1
                with page.expect_response(
                    lambda item: item.url.endswith("/faction-intercept")
                ) as pending:
                    target_row.get_by_role(
                        "button", name="截杀"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.locator("#battle-report-card").is_visible()

                demonic = engine.create_game(
                    "御傀界面烟测", seed=702, path="demonic",
                    start_world="demon",
                )
                demonic_id = str(demonic["id"])
                demonic_actor = str(demonic["player"]["id"])
                demonic_state = engine.store.load(demonic_id)
                demonic_cultivation = demonic_state.entities.require(
                    demonic_actor, "cultivation.state"
                )
                demonic_cultivation.update(
                    realm_id="core", layer=3, opportunity=10_000.0
                )
                demonic_state.entities.put(
                    demonic_actor, "cultivation.state", demonic_cultivation
                )
                engine.store.save(
                    demonic_state, [], player_name="御傀界面烟测",
                    expected_revision=demonic_state.revision,
                )
                before = set(
                    engine.store.load(demonic_id).entities.with_component(
                        "core.identity"
                    )
                )
                engine.execute(
                    demonic_id,
                    RegisterCharacter(
                        "伏兵", 24, "male", "human", "supreme_wood",
                        "dao", "mortal", 1, "demon",
                    ),
                )
                after = set(
                    engine.store.load(demonic_id).entities.with_component(
                        "core.identity"
                    )
                )
                captive_id = (after - before).pop()
                engine.execute(
                    demonic_id,
                    ResolveCombat(demonic_actor, captive_id, "capture"),
                )
                page.evaluate("id => loadGame(id)", demonic_id)
                page.locator("body:not(.busy)").wait_for()
                if page.locator("#battle-report-card").is_visible():
                    page.locator("#battle-report-toggle").click()
                page.locator('[data-panel-target="captive"]').click(force=True)
                captive = page.locator(
                    "#captive-list .captive-row"
                ).filter(has_text="伏兵")
                assert captive.count() == 1
                captive_text = captive.text_content()
                assert "战力" in captive_text
                assert "undefined" not in captive_text
                assert "NaN" not in captive_text
                with page.expect_response(
                    lambda item: item.url.endswith("/captive-action")
                ) as pending:
                    captive.get_by_role("button", name="拷打").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                captive = page.locator(
                    "#captive-list .captive-row"
                ).filter(has_text="伏兵")
                with page.expect_response(
                    lambda item: item.url.endswith("/captive-action")
                ) as pending:
                    captive.get_by_role("button", name="种下标记").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                puppet = page.locator(
                    "#puppet-list .puppet-row"
                ).filter(has_text="伏兵")
                assert puppet.count() == 1
                puppet_text = puppet.text_content()
                assert "控制度" in puppet_text
                assert "队伍战力" in puppet_text
                assert "undefined" not in puppet_text
                assert "NaN" not in puppet_text
                with page.expect_response(
                    lambda item: item.url.endswith("/puppet-action")
                ) as pending:
                    puppet.get_by_role(
                        "button", name="加固控制", exact=False
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                puppet = page.locator(
                    "#puppet-list .puppet-row"
                ).filter(has_text="伏兵")
                with page.expect_response(
                    lambda item: item.url.endswith("/puppet-action")
                ) as pending:
                    puppet.get_by_role("button", name="吞噬").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                soul = page.locator("#foreign-soul-list .soul-row").filter(
                    has_text="伏兵之元神"
                )
                assert soul.count() == 1
                before_refine = soul.text_content()
                with page.expect_response(
                    lambda item: item.url.endswith("/refine-souls")
                ) as pending:
                    page.locator("#refine-souls").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                soul = page.locator("#foreign-soul-list .soul-row").filter(
                    has_text="伏兵之元神"
                )
                assert soul.text_content() != before_refine
                assert not page.locator("#secluded-refine-souls").is_disabled()
                with page.expect_response(
                    lambda item: item.url.endswith(
                        "/secluded-refine-souls"
                    )
                ) as pending:
                    page.locator("#secluded-refine-souls").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.locator(
                    "#foreign-soul-list .soul-archive"
                ).count() == 1
                while page.evaluate("game.pending_event !== null"):
                    choice = page.locator(
                        "#event-choices button:not([disabled])"
                    ).first
                    assert choice.count() == 1
                    with page.expect_response(
                        lambda item: item.url.endswith("/choice")
                    ) as pending:
                        choice.click()
                    assert pending.value.status == 200, pending.value.text()
                    page.locator("body:not(.busy)").wait_for()
                before = set(
                    engine.store.load(demonic_id).entities.with_component(
                        "core.identity"
                    )
                )
                engine.execute(
                    demonic_id,
                    RegisterCharacter(
                        "旧识", 24, "male", "human", "supreme_wood",
                        "dao", "mortal", 1, "demon",
                    ),
                )
                after = set(
                    engine.store.load(demonic_id).entities.with_component(
                        "core.identity"
                    )
                )
                old_friend_id = (after - before).pop()
                engine.execute(
                    demonic_id,
                    FormRelationship(
                        demonic_actor, old_friend_id, "friend"
                    ),
                )
                engine.change_affinity(demonic_id, old_friend_id, 60)
                page.evaluate("id => loadGame(id)", demonic_id)
                page.locator("body:not(.busy)").wait_for()
                page.locator(
                    '[data-panel-target="relationship"]'
                ).click(force=True)
                friend_capture = page.locator(
                    "#dao-friend-list .friend-row"
                ).filter(has_text="旧识")
                with page.expect_response(
                    lambda item: item.url.endswith("/relationship-capture")
                ) as pending:
                    friend_capture.get_by_role(
                        "button", name="尝试生擒"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()

                celestial = engine.create_game(
                    "天庭界面烟测", seed=20260919
                )
                celestial_id = str(celestial["id"])
                celestial_actor = str(celestial["player"]["id"])
                celestial_state = engine.store.load(celestial_id)
                celestial_location = celestial_state.entities.require(
                    celestial_actor, "world.location"
                )
                celestial_location.update(
                    world_id="celestial",
                    location_id=engine.definitions.default_location(
                        "celestial"
                    ),
                )
                celestial_state.entities.put(
                    celestial_actor, "world.location", celestial_location
                )
                celestial_cultivation = celestial_state.entities.require(
                    celestial_actor, "cultivation.state"
                )
                celestial_cultivation.update(
                    realm_id=engine.definitions.realms[9].id, layer=1
                )
                celestial_state.entities.put(
                    celestial_actor, "cultivation.state",
                    celestial_cultivation,
                )
                celestial_life = celestial_state.entities.require(
                    celestial_actor, "character.life"
                )
                celestial_life["lifespan"] = None
                celestial_state.entities.put(
                    celestial_actor, "character.life", celestial_life
                )
                reconcile_celestial_state(
                    celestial_state, engine.definitions
                )
                court_id = celestial_state.entities.with_component(
                    CELESTIAL_COURT
                )[0]
                court = celestial_state.entities.require(
                    court_id, CELESTIAL_COURT
                )
                court["player_grade"] = 4
                court["player_merit"] = 10**6
                first_office = next(iter(court["offices"]))
                court["offices"][first_office] = {
                    "holder_id": celestial_actor,
                    "holder_name": "天庭界面烟测",
                    "start_unit": 0,
                    "end_unit": 7,
                    "votes": 13,
                }
                celestial_state.entities.put(
                    court_id, CELESTIAL_COURT, court
                )
                engine.store.save(
                    celestial_state, [], player_name="天庭界面烟测",
                    expected_revision=celestial_state.revision,
                )
                page.evaluate("id => loadGame(id)", celestial_id)
                page.locator("body:not(.busy)").wait_for()
                court_dock = page.locator(
                    '[data-panel-target="heavenly-court"]'
                )
                assert court_dock.is_visible()
                court_dock.click(force=True)
                assert page.locator(
                    "#heavenly-court-content .court-offices > div"
                ).count() == 7
                assert page.locator(
                    "#heavenly-court-content .court-offices .player-held"
                ).count() == 1
                court_text = page.locator(
                    "#heavenly-court-content"
                ).text_content()
                assert "天庭界面烟测（你）" in court_text
                assert "undefined" not in court_text
                assert "NaN" not in court_text
                exam = page.get_by_role(
                    "button", name="接受进阶考核"
                )
                assert exam.is_enabled()
                with page.expect_response(
                    lambda item: item.url.endswith("/heavenly-court")
                ) as pending:
                    exam.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()

                celestial_state = engine.store.load(celestial_id)
                court = celestial_state.entities.require(
                    court_id, CELESTIAL_COURT
                )
                court["player_grade"] = 4
                celestial_state.entities.put(
                    court_id, CELESTIAL_COURT, court
                )
                engine.store.save(
                    celestial_state, [], player_name="天庭界面烟测",
                    expected_revision=celestial_state.revision,
                )
                election_years = engine.definitions.action_time(
                    engine.definitions.realms[9].id, 1
                ) * 2
                paused = engine.perform_timed_action(
                    celestial_id, "rest", election_years
                ).game
                assert paused["heavenly_court"]["election"] is not None
                page.evaluate("id => loadGame(id)", celestial_id)
                page.locator("body:not(.busy)").wait_for()
                if not page.locator("#heavenly-court-card").evaluate(
                    "node => node.classList.contains('panel-open')"
                ):
                    court_dock.click(force=True)
                election = page.locator(
                    "#heavenly-court-content .court-election"
                )
                assert election.count() == 1
                election_text = election.text_content()
                assert "候选" in election_text
                assert "undefined" not in election_text
                assert "NaN" not in election_text
                with page.expect_response(
                    lambda item: item.url.endswith("/heavenly-election")
                ) as pending:
                    election.get_by_role(
                        "button", name="完成本轮投票（不流逝时间）"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()

                lineage = engine.create_game(
                    "祖血界面烟测", seed=8800, path="monster",
                    start_world="phantom_underworld",
                    monster_species_id="serpent",
                )
                lineage_id = str(lineage["id"])
                lineage_actor = str(lineage["player"]["id"])
                lineage_state = engine.store.load(lineage_id)
                lineage_cultivation = lineage_state.entities.require(
                    lineage_actor, "cultivation.state"
                )
                lineage_cultivation.update(
                    realm_id="mahayana",
                    layer=engine.definitions.realm("mahayana").layers,
                    opportunity=10**18,
                    bottleneck="major",
                )
                lineage_state.entities.put(
                    lineage_actor, "cultivation.state", lineage_cultivation
                )
                lineage_blood = lineage_state.entities.require(
                    lineage_actor, "dlc.monster.bloodline"
                )
                lineage_blood.update(
                    evolution_id="SERPENT_MAHAYANA_DRAGON",
                    evolution_history=[
                        "SERPENT_BASE", "SERPENT_MAHAYANA_DRAGON"
                    ],
                )
                lineage_state.entities.put(
                    lineage_actor, "dlc.monster.bloodline", lineage_blood
                )
                engine.store.save(
                    lineage_state, [], player_name="祖血界面烟测",
                    expected_revision=lineage_state.revision,
                )
                page.evaluate("id => loadGame(id)", lineage_id)
                page.locator("body:not(.busy)").wait_for()
                page.locator(
                    '[data-panel-target="bloodline"]'
                ).click(force=True)
                self_route = page.locator(
                    ".bloodline-candidate"
                ).filter(has_text="万界蛇祖")
                assert self_route.count() == 1
                with page.expect_response(
                    lambda item: item.url.endswith("/custom-lineage-prepare")
                ) as pending:
                    self_route.get_by_role(
                        "button", name="选择进化"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                editor = page.locator(".custom-lineage-editor")
                editor.locator("input").fill("万界自在脉")
                editor.get_by_role("button", name="追加规则").click()
                assert editor.locator(".custom-lineage-rule").count() == 1
                assert "当前配置合法" in editor.locator(
                    ".custom-lineage-invalid"
                ).text_content()
                with page.expect_response(
                    lambda item: item.url.endswith("/custom-lineage-confirm")
                ) as pending:
                    editor.get_by_role(
                        "button", name="确认立祖并进化"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert "万界自在脉" in page.locator(
                    ".custom-lineage-summary"
                ).text_content()
                assert page.evaluate("game.player.realm_index") == 9

                ghost = engine.create_game(
                    "鬼修富状态烟测", seed=8801, path="ghost",
                    start_world="hell",
                )
                ghost_id = str(ghost["id"])
                ghost_actor = str(ghost["player"]["id"])
                engine.execute(
                    ghost_id,
                    GrantItem(ghost_actor, "soul_lamp", 1, "browser-smoke"),
                )
                known = set(
                    engine.store.load(ghost_id).entities.with_component(
                        "core.identity"
                    )
                )
                engine.execute(
                    ghost_id,
                    RegisterCharacter(
                        "伏矢烟魂", 35, "male", "human", "none", "ghost",
                        "foundation", 3, "hell",
                    ),
                )
                ghost_state = engine.store.load(ghost_id)
                soul_id = next(iter(
                    set(ghost_state.entities.with_component("core.identity"))
                    - known
                ))
                ghost_state.entities.put(soul_id, "dlc.ghost.bound_soul", {
                    "name": "伏矢烟魂",
                    "origin": "browser-smoke",
                    "status": "bound",
                    "combat_power": 180.0,
                    "soul_pressure": 1.2,
                    "affinity": 20,
                    "defeated": True,
                    "befriended": False,
                    "trait": {
                        "name": "凶魂",
                        "description": "对衰弱敌人增伤",
                    },
                })
                ghost_state.relations.add(
                    source_id=ghost_actor,
                    target_id=soul_id,
                    kind="dlc.ghost.soul_control",
                    created_year=ghost_state.clock.year,
                    metadata={"status": "bound"},
                )
                ghost_cultivation = ghost_state.entities.require(
                    ghost_actor, "cultivation.state"
                )
                ghost_cultivation.update(
                    realm_id="core",
                    layer=engine.definitions.realm("core").layers,
                    bottleneck="major",
                    opportunity=999_999.0,
                )
                ghost_state.entities.put(
                    ghost_actor, "cultivation.state", ghost_cultivation
                )
                ghost_soul = ghost_state.entities.require(
                    ghost_actor, "dlc.ghost.soul"
                )
                ghost_soul.update(wangsheng=5, erosion_rate_pp=0.08)
                ghost_state.entities.put(
                    ghost_actor, "dlc.ghost.soul", ghost_soul
                )
                engine.store.save(
                    ghost_state, [], player_name="鬼修富状态烟测",
                    expected_revision=ghost_state.revision,
                )
                page.evaluate("id => loadGame(id)", ghost_id)
                page.locator("body:not(.busy)").wait_for()
                assert "自由魂体" in page.locator(
                    "#ghost-phase-state"
                ).text_content()
                page.locator(
                    '[data-panel-target="ghost-soul"]'
                ).click(force=True)
                assert page.locator(
                    "#ghost-soul-slots .captive-row"
                ).count() == 10
                bound_row = page.locator(
                    "#ghost-bound-souls .captive-row"
                ).filter(has_text="伏矢烟魂")
                assert "凶魂" in bound_row.text_content()
                with page.expect_response(
                    lambda item: item.url.endswith("/ghost-soul")
                ) as pending:
                    bound_row.get_by_role("button", name="入魂位").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                occupied_slot = page.locator(
                    "#ghost-soul-slots .captive-row"
                ).filter(has_text="伏矢烟魂")
                assert occupied_slot.count() == 1
                # The frozen V1 bundle itself leaves this dynamically rebuilt
                # button disabled after a mutation.  Domain coverage verifies
                # unequip; preserving that baseline client quirk is intentional.
                assert occupied_slot.get_by_role(
                    "button", name="卸下"
                ).is_disabled()

                page.locator(
                    '[data-panel-target="ghost-attachment"]'
                ).click(force=True)
                attach = page.locator(
                    "#ghost-attachment-list button"
                ).filter(has_text="附入 守命魂灯")
                assert attach.is_enabled()
                with page.expect_response(
                    lambda item: item.url.endswith("/ghost-attachment")
                ) as pending:
                    attach.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert "守命魂灯器灵·鬼修富状态烟测" in page.locator(
                    "#ghost-attachment-list"
                ).text_content()
                with page.expect_response(
                    lambda item: item.url.endswith("/ghost-attachment")
                ) as pending:
                    page.locator("#ghost-attachment-list").get_by_role(
                        "button", name="离器"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.locator(
                    "#ghost-attachment-summary"
                ).text_content() == "自由魂体"

                parade_state = engine.store.load(ghost_id)
                parade_location = parade_state.entities.require(
                    ghost_actor, "world.location"
                )
                parade_ecology = parade_state.entities.require(
                    ghost_actor, "dlc.ghost.ecology"
                )
                parade_ecology["parade"] = {
                    "status": "active",
                    "world_id": parade_location["world_id"],
                    "location_id": parade_location["location_id"],
                    "start_year": parade_state.clock.year,
                    "end_year": parade_state.clock.year + 100,
                    "announced": True,
                    "participated": False,
                    "soul_ids": [],
                }
                parade_state.entities.put(
                    ghost_actor, "dlc.ghost.ecology", parade_ecology
                )
                engine.store.save(
                    parade_state, [], player_name="鬼修富状态烟测",
                    expected_revision=parade_state.revision,
                )
                page.evaluate("id => loadGame(id)", ghost_id)
                page.locator("body:not(.busy)").wait_for()
                page.locator(
                    '[data-panel-target="ghost-parade"]'
                ).click(force=True)
                parade_join = page.locator(
                    "#ghost-parade-list"
                ).get_by_role("button", name="参悟夜行")
                # Frozen V1 creates these dynamic ghost buttons while busy
                # and never re-enables them in renderButtons().  Preserve the
                # baseline bundle, but unlock the original client defect here
                # so the V1 payload and V2 endpoint are still integration-tested.
                parade_join.evaluate("node => node.disabled = false")
                with page.expect_response(
                    lambda item: item.url.endswith("/ghost-parade")
                ) as pending:
                    parade_join.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.locator("#ghost-parade-list").get_by_role(
                    "button", name="本次已参悟"
                ).is_disabled()

                possession_known = set(
                    engine.store.load(ghost_id).entities.with_component(
                        "core.identity"
                    )
                )
                engine.execute(
                    ghost_id,
                    RegisterCharacter(
                        "夺舍备用身", 28, "male", "human", "none", "dao",
                        "mortal", 1, "hell",
                    ),
                )
                possession_state = engine.store.load(ghost_id)
                possession_target = next(iter(
                    set(possession_state.entities.with_component("core.identity"))
                    - possession_known
                ))
                engine.execute(
                    ghost_id,
                    ResolveCombat(ghost_actor, possession_target, "capture"),
                )
                possession_state = engine.store.load(ghost_id)
                ghost_life = possession_state.entities.require(
                    ghost_actor, "character.life"
                )
                ghost_life.update(alive=False, death_reason="浏览器夺舍烟测")
                possession_state.entities.put(
                    ghost_actor, "character.life", ghost_life
                )
                demonic_state = possession_state.entities.require(
                    ghost_actor, "demonic.state"
                )
                demonic_state["pending_post_battle_possession"] = {
                    "candidate_ids": [possession_target],
                    "year": possession_state.clock.year,
                }
                possession_state.entities.put(
                    ghost_actor, "demonic.state", demonic_state
                )
                engine.store.save(
                    possession_state, [], player_name="鬼修富状态烟测",
                    expected_revision=possession_state.revision,
                )
                page.evaluate("id => loadGame(id)", ghost_id)
                page.locator("body:not(.busy)").wait_for()
                if page.locator("#battle-report-card").is_visible():
                    page.locator("#battle-report-toggle").click()
                possession_choice = page.locator(
                    "#post-battle-possession-choices "
                    ".post-battle-possession-choice"
                ).filter(has_text="夺舍备用身")
                assert possession_choice.count() == 1
                with page.expect_response(
                    lambda item: item.url.endswith(
                        "/post-battle-possession"
                    )
                ) as pending:
                    possession_choice.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert "夺舍寄身" in page.locator(
                    "#ghost-phase-state"
                ).text_content()
                browser_ghost_phase = page.evaluate(
                    "game.ghost_system.phase_two"
                )
                assert browser_ghost_phase["state"] == "possessed", (
                    browser_ghost_phase,
                    page.locator("#ghost-host-actions").inner_html(),
                    errors,
                )
                if "panel-open" not in (
                    page.locator("#ghost-soul-card").get_attribute("class")
                    or ""
                ):
                    page.locator(
                        '[data-panel-target="ghost-soul"]'
                    ).click(force=True)
                page.once("dialog", lambda dialog: dialog.accept())
                leave_host = page.locator(
                    "#ghost-host-actions button"
                )
                assert leave_host.count() == 1, (
                    browser_ghost_phase,
                    page.locator("#ghost-host-actions").inner_html(),
                    errors,
                )
                leave_host.evaluate("node => node.disabled = false")
                with page.expect_response(
                    lambda item: item.url.endswith("/ghost-leave-host")
                ) as pending:
                    leave_host.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert "自由魂体" in page.locator(
                    "#ghost-phase-state"
                ).text_content()

                captor_known = set(
                    engine.store.load(ghost_id).entities.with_component(
                        "core.identity"
                    )
                )
                engine.execute(
                    ghost_id,
                    RegisterCharacter(
                        "拘魂烟测者", 60, "female", "human", "none", "ghost",
                        "foundation", 1, "hell",
                    ),
                )
                constraint_state = engine.store.load(ghost_id)
                captor_id = next(iter(
                    set(constraint_state.entities.with_component("core.identity"))
                    - captor_known
                ))
                constraint_ecology = constraint_state.entities.require(
                    ghost_actor, "dlc.ghost.ecology"
                )
                constraint_ecology["captor"] = {
                    "entity_id": captor_id,
                    "name": "拘魂烟测者",
                    "combat_power": 100.0,
                    "followed_years": 0,
                }
                constraint_state.entities.put(
                    ghost_actor, "dlc.ghost.ecology", constraint_ecology
                )
                engine.store.save(
                    constraint_state, [], player_name="鬼修富状态烟测",
                    expected_revision=constraint_state.revision,
                )
                page.evaluate("id => loadGame(id)", ghost_id)
                page.locator("body:not(.busy)").wait_for()
                constraint_wait = page.locator(
                    "#ghost-constraint-actions"
                ).get_by_role("button", name="忍耐一年")
                constraint_wait.evaluate("node => node.disabled = false")
                with page.expect_response(
                    lambda item: item.url.endswith("/ghost-constraint")
                ) as pending:
                    constraint_wait.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert "拘魂烟测者" in page.locator(
                    "#ghost-constraint-actions"
                ).text_content()
                constraint_state = engine.store.load(ghost_id)
                constraint_ecology = constraint_state.entities.require(
                    ghost_actor, "dlc.ghost.ecology"
                )
                constraint_ecology["captor"] = None
                constraint_state.entities.put(
                    ghost_actor, "dlc.ghost.ecology", constraint_ecology
                )
                engine.store.save(
                    constraint_state, [], player_name="鬼修富状态烟测",
                    expected_revision=constraint_state.revision,
                )
                page.evaluate("id => loadGame(id)", ghost_id)
                page.locator("body:not(.busy)").wait_for()
                if "panel-open" in (
                    page.locator("#ghost-soul-card").get_attribute("class")
                    or ""
                ):
                    page.locator("#ghost-soul-toggle").click()
                while page.evaluate("game.pending_event !== null"):
                    choice = page.locator(
                        "#event-choices button:not([disabled])"
                    ).first
                    with page.expect_response(
                        lambda item: item.url.endswith("/choice")
                    ) as pending:
                        choice.click()
                    assert pending.value.status == 200, pending.value.text()
                    page.locator("body:not(.busy)").wait_for()
                current_ghost = page.evaluate("game.ghost_system")
                assert current_ghost.get("available"), current_ghost
                assert page.locator("#ghost-system-panel").is_visible(), (
                    current_ghost,
                    page.locator("#ghost-system-panel").get_attribute("class"),
                    page.evaluate("game.player"),
                )

                with page.expect_response(
                    lambda item: item.url.endswith("/ghost-wangsheng")
                ) as pending:
                    page.locator("#ghost-wangsheng-all-action").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.locator("#ghost-wangsheng").text_content() == "1"
                with page.expect_response(
                    lambda item: item.url.endswith(
                        "/ghost-reincarnation-prompt"
                    )
                ) as pending:
                    page.locator("#ghost-reincarnate-action").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("#event-card").wait_for(state="visible")
                cancel = page.locator(
                    "#event-choices button:not([disabled])"
                ).filter(has_text="取消")
                with page.expect_response(
                    lambda item: item.url.endswith("/choice")
                ) as pending:
                    cancel.click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.locator("#event-card").is_hidden()
                assert_visible_panels_clean(page)

                upper = engine.create_game("上界浏览器", seed=8888)
                upper_state = engine.store.load(upper["id"])
                upper_actor = str(upper_state.controlled_entity_id)
                upper_cultivation = upper_state.entities.require(
                    upper_actor, "cultivation.state"
                )
                upper_cultivation.update(
                    realm_id="mahayana", layer=9, opportunity=10**9
                )
                upper_state.entities.put(
                    upper_actor, "cultivation.state", upper_cultivation
                )
                upper_location = upper_state.entities.require(
                    upper_actor, "world.location"
                )
                upper_location.update(
                    world_id="spirit",
                    location_id=engine.definitions.default_location("spirit"),
                )
                upper_state.entities.put(
                    upper_actor, "world.location", upper_location
                )
                engine.store.save(
                    upper_state, [], player_name="上界浏览器",
                    expected_revision=upper_state.revision,
                )
                upper_known = set(
                    engine.store.load(upper["id"]).entities.with_component(
                        "core.identity"
                    )
                )
                engine.execute(
                    upper["id"],
                    RegisterCharacter(
                        "青角外援", 80, "male", "monster", "supreme_wood",
                        "monster", "core", 1, "spirit",
                    ),
                )
                upper_state = engine.store.load(upper["id"])
                upper_vassal_candidate = next(iter(
                    set(upper_state.entities.with_component("core.identity"))
                    - upper_known
                ))
                page.evaluate("id => loadGame(id)", upper["id"])
                page.locator("body:not(.busy)").wait_for()
                assert page.locator("[data-panel-target='ranking']").is_visible()
                assert page.locator("[data-panel-target='race']").is_visible()
                assert page.locator("#ranking-list .ranking-row").count() > 0
                assert page.locator("#race-list .race-chip").count() > 0
                upper_text = page.locator("body").inner_text()
                assert "NaN" not in upper_text
                assert "undefined" not in upper_text
                assert "天机数 null" not in upper_text

                page.locator('[data-panel-target="race"]').click(force=True)
                target_race = page.locator(
                    "#race-list .race-chip:not(.current)"
                ).filter(has_text="妖").first
                assert target_race.count() == 1
                target_race.click()
                race_diplomacy = page.locator(
                    "#race-detail .diplomacy-form"
                )
                race_diplomacy.locator("select").nth(1).select_option(
                    "vassal"
                )
                with page.expect_response(
                    lambda item: item.url.endswith("/race-diplomacy")
                ) as pending:
                    race_diplomacy.get_by_role(
                        "button", name="提交表决"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                target_race = page.locator(
                    "#race-list .race-chip:not(.current)"
                ).filter(has_text="妖").first
                target_race.click()
                transfer = page.locator(
                    "#race-detail .governance-form"
                ).filter(has_text="调遣外援")
                assert transfer.count() == 1
                transfer.locator("select").select_option(
                    upper_vassal_candidate
                )
                with page.expect_response(
                    lambda item: item.url.endswith("/vassal-transfer")
                ) as pending:
                    transfer.get_by_role(
                        "button", name="执行调动"
                    ).click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                page.locator(
                    "#race-list .race-chip:not(.current)"
                ).filter(has_text="妖").first.click()
                assert "青角外援" in page.locator("body").text_content()
                page.locator("#race-toggle").click()

                assert page.locator("#cross-world-action").is_visible()
                assert "人界" in page.locator(
                    "#cross-world-title"
                ).text_content()
                with page.expect_response(
                    lambda item: item.url.endswith("/cross-world")
                ) as pending:
                    page.locator("#cross-world-action").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.evaluate("game.player.world") == "human"
                assert page.locator("#cross-world-action").is_visible()
                with page.expect_response(
                    lambda item: item.url.endswith("/cross-world")
                ) as pending:
                    page.locator("#cross-world-action").click()
                assert pending.value.status == 200, pending.value.text()
                page.locator("body:not(.busy)").wait_for()
                assert page.evaluate("game.player.world") == "spirit"

                assert_visible_panels_clean(page)

                page.locator('[data-panel-target="settings"]').click(force=True)
                with page.expect_response(
                    lambda item: item.url.endswith("/debug-world-news")
                ) as pending:
                    page.locator("#world-news-debug").click()
                assert pending.value.status == 200
                page.locator("body:not(.busy)").wait_for()
                assert "开" in page.locator("#world-news-debug").text_content()

                before = page.locator("#age-line").text_content()
                with page.expect_response(
                    lambda item: item.url.endswith("/advance")
                ) as pending:
                    page.locator('[data-action="cultivate"]').click()
                assert pending.value.status == 200
                page.locator("body:not(.busy)").wait_for()
                assert page.locator("#age-line").text_content() != before

                page.set_viewport_size({"width": 390, "height": 844})
                page.locator('[data-panel-target="map"]').evaluate("node => node.click()")
                assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
                assert not errors, errors
                assert not console_errors, console_errors
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    main()
