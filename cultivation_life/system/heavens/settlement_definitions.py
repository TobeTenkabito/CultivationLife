"""Fixed local settlement terms, deliberately independent of faction politics."""
from ...definition_data import definition as _content_definition

CONTROL_NAMES = {'original': '原有秩序', 'contested': '双方争持', 'occupied': '军事占领',
                 'vassal': '限期附约', 'uncontrolled': '驻防中断', 'restored': '守方重新驻防'}
TREATY_NAMES = {'truce': '岚疆停战', 'vassal': '岚疆限期附约', 'withdrawal': '修复后撤军'}
LABELS = {'campaign_truce': '提出当地停战', 'campaign_vassal': '提出限期附约',
          'campaign_withdrawal': '出示修复凭据并议撤军', 'campaign_relief': '救护现场伤员',
          'campaign_release': '释放原俘虏并准其返乡',
          'campaign_evacuate': '沿原道路撤往无棣原'}
TERM_YEARS = 30
ADMIN_COST = 100
CLAUSES = _content_definition(__name__, "CLAUSES")
