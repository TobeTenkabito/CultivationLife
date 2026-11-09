"""3.6.1: original building integration, consolidated navigation and temple art."""
TESTS = [
    'test_yaochi_westward', 'test_earth_temple', 'test_earth_network', 'test_earth_disputes',
    'test_court_bureaus', 'test_court_justice', 'test_yaochi_fair', 'test_westward_ventures',
    'test_westward_finale', 'test_yaochi_guidance', 'test_westward_schedule',
    'test_immortal_cultivation', 'test_immortal_body_and_resources', 'test_divine_lights',
    'test_heavenly_court_system', 'test_yaochi_governance_1511', 'test_court_dependencies',
    'test_building_system', 'test_city_buildings', 'test_city_management', 'test_building_visits',
    'test_economy_enterprises', 'test_economy_estate_audit', 'test_economy_governance',
    'test_organization_economy', 'test_economy_network', 'test_regional_calendar',
    'test_formation_system', 'test_npc_development', 'test_npc_development_upper',
    'test_npc_combat_lifecycle', 'test_survival_settlement', 'test_ghost_system',
    'test_three_group_dependencies', 'test_heavens_incidents', 'test_heavens_missions',
    'test_heavens_campaign', 'test_player_combat_system', 'test_time_flow',
    'test_world_transition_system', 'test_spatial_talismans', 'test_release_211', 'test_release_212',
    'test_extension_system', 'test_persistence_pipeline', 'test_save_transfer',
    'test_base_game_version', 'test_module_dependencies', 'test_android_packaging',
    'test_windows_release_evidence', 'test_android_release_checks',
    'test_ui_preferences', 'test_visual_release', 'test_pixel_assets', 'test_temple_art', 'test_home_scenes',
]
TESTS = ['tests/' + name + '.py' for name in TESTS]
BROWSERS = ['browser_yaochi_westward', 'browser_earth_temple', 'browser_earth_network',
            'browser_earth_disputes', 'browser_court_bureaus', 'browser_court_justice',
            'browser_yaochi_fair', 'browser_westward_ventures', 'browser_westward_finale', 'browser_dlc_controls',
            'browser_events_212', 'browser_desktop_navigation', 'browser_caravan_trust_audit','browser_home_scenes']
SCOPE = '3.6.1 Westward 1.0: eight gameplay lines, four-chapter mainline and four endings, exclusive identities, merit repair and actual-teacher guidance; DLC ownership styling in both pixel palettes, original court/building/economy/NPC/combat/time/transition/persistence upstreams; real browser submissions, EXE with/without DLC, signed Android 12 portrait/landscape; not full repository regression'
