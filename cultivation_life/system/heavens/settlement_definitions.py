"""Fixed local settlement terms, deliberately independent of faction politics."""

CONTROL_NAMES = {'original': '原有秩序', 'contested': '双方争持', 'occupied': '军事占领',
                 'vassal': '限期附约', 'uncontrolled': '驻防中断', 'restored': '守方重新驻防'}
TREATY_NAMES = {'truce': '岚疆停战', 'vassal': '岚疆限期附约', 'withdrawal': '修复后撤军'}
LABELS = {'campaign_truce': '提出当地停战', 'campaign_vassal': '提出限期附约',
          'campaign_withdrawal': '出示修复凭据并议撤军', 'campaign_relief': '救护现场伤员',
          'campaign_release': '释放原俘虏并准其返乡',
          'campaign_evacuate': '沿原道路撤往无棣原'}
TERM_YEARS = 30
ADMIN_COST = 100
CLAUSES = {
    'truce': ['仅停止岚疆双方部署人员之间的交战。', '双方沿原许可撤回；普通修行、通行及救护不受禁止。',
              '不处分宗门、全界、其他地点或玩家身份；不支付赔款。'],
    'vassal': ['仅岚疆守备在三十年内接受血狱驻军监督；天剑宗其余事务不在约内。',
               '原守备负责当地秩序，来方驻军承担护路；两方均须在场并有实有经费。',
               '不征税、不征发玩家或新兵；不得越过岚疆扩张。期满或失能即结束驻防。'],
    'withdrawal': ['须现场核验原关联阵眼已恢复。', '血狱部署沿已有单人路线撤离，不附加军事入境权。',
                   '原物权、伤势和拘禁事实保留，签约不传送或复活任何人物。'],
}
