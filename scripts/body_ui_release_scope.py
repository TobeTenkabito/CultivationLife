"""3.5.1 declared changed domains/upstreams; no full-repository claim."""
TESTS=[
 'test_upper_social_351','test_npc_social_assets','test_npc_contacts','test_authored_techniques',
 'test_ui_preferences','test_visual_release','test_pixel_assets','test_tutorial','test_tutorial_walkthrough',
 'test_divine_lights','test_body_round_wuyun','test_ghost_body','test_ghost_body_events','test_ghost_body_materials',
 'test_monster_body','test_wuyun_materials','test_high_body_audit','test_high_body_balance','test_high_body_cultivation_audit',
 'test_field_disciplines','test_field_discipline_boundaries','test_asura_pressure','test_feixue_recovery',
 'test_trial_pressure','test_restore_threshold','test_upper_breakthrough_calibration',
 'test_combat_semantics','test_voisinage_effects','test_immortal_cultivation','test_immortal_trials',
 'test_asura_manifestation','test_asura_system','test_asura_hotfix','test_asura_dependencies','test_upper_voisinages',
 'test_player_combat_system','test_domain_combat','test_combat_replay','test_survival_settlement','test_soul_lifecycle',
 'test_npc_combat_lifecycle','test_spirit_inheritance','test_immortal_artifacts','test_natal_artifact_system',
 'test_persistence_pipeline','test_save_transfer','test_release_212','test_release_211','test_world_transition_system',
 'test_spatial_talismans','test_base_game_version','test_module_dependencies','test_android_packaging',
 'test_windows_release_evidence','test_android_release_checks','test_extension_system','test_body_ui_release',
]
TESTS=['tests/'+name+'.py' for name in TESTS]
BROWSERS=['browser_upper_social_351','browser_body_ui_release','browser_eightfold','browser_divine_lights','browser_wuyun',
 'browser_monster_body','browser_ghost_body','browser_desktop_navigation','browser_events_212','browser_pixel_only']
SCOPE='3.5.1 upper-world guide, NPC portraits and authored DLC naming plus four high-body families, eightfold mechanics, pixel-only two-palette UI, source/persistence/combat and release upstreams; not full repository regression'
