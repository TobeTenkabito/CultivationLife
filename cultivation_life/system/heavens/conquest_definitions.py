"""Explicit local military mandate; civilian crossing permissions stay separate."""
LABELS = {'outpost_military_authorize': '总部批准当地征战',
          'outpost_war_start': '派驻地门人出征', 'outpost_war_fight': '亲赴战场参战',
          'outpost_war_vassal': '按战果签订归附和约', 'outpost_war_stop': '停战并循路撤军',
          'outpost_war_settle': '结清归返军需'}
OPTIONS = {key: set() for key in LABELS}
OPTIONS['outpost_war_start'] = {'person_id', 'rival_id'}
WAR_BUDGET = 30000
BATTLE_INTERVAL = 10
WAR_LIMIT = 6
CAMPAIGN_PHASE = 'campaign'
