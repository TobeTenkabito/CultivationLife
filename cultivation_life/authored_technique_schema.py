"""Finite, non-executable authoring vocabulary shared by saves and the editor."""
import math

PREFIX = 'TECH_AUTHORED_'
SLOTS = {'main': '主修', 'support': '辅修', 'combat': '战斗', 'body': '炼体', 'sense': '神识', 'transformation': '变化'}
STATS = {'opportunity_bonus': '机缘', 'hp_bonus': '气血', 'mp_bonus': '法力', 'combat_bonus': '战力'}
# label, semantic phase, semantic channel, maximum percentage, point price per percent
EFFECTS = {
    'might': ('普通威能', 'ordinary_start', 'ordinary.might', 50, 3),
    'guard': ('普通防护', 'ordinary_start', 'ordinary.guard', 50, 3),
    'mobility': ('普通身法', 'ordinary_start', 'ordinary.mobility', 50, 2),
    'sense': ('普通神识', 'ordinary_start', 'ordinary.sense', 50, 2),
    'breach': ('普通破法', 'ordinary_start', 'ordinary.breach', 50, 3),
    'sustain': ('普通续航', 'ordinary_start', 'ordinary.sustain', 50, 2),
    'strike': ('邻域杀伤', 'effect_before_apply', 'field.strike', 50, 4),
    'incursion': ('邻域侵夺', 'contest_prepare', 'field.incursion', 50, 4),
    'stability': ('邻域稳固', 'contest_prepare', 'field.stability', 50, 4),
    'upkeep': ('邻域维持消耗降低', 'field_prepare', 'field.upkeep_cost', 50, 4),
    'restore': ('回复最大战斗态势', 'round_start', 'state', 10, 12),
}


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label}须为 {low}–{high} 的整数')
    return value


def validate_buffs(rows):
    if not isinstance(rows, list) or len(rows) > 4:
        raise ValueError('每部功法最多四条效果')
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'slot', 'effect', 'value', 'level', 'condition', 'round'}:
            raise ValueError('效果仅允许栏目、等级、一个条件及一种效果')
        if row['slot'] not in SLOTS or row['effect'] not in EFFECTS or row['condition'] not in {'always', 'from_round', 'at_round'}:
            raise ValueError('未知功法效果')
        integer(row['value'], 1, EFFECTS[row['effect']][3], '效果数值')
        integer(row['level'], 1, 9, '解锁等级')
        integer(row['round'], 1, 8, '起始轮次')
        if row['condition'] == 'always' and row['round'] != 1:
            raise ValueError('常驻效果无需附加轮次')
    return rows


def buff_text(row):
    effect = EFFECTS[row['effect']][0]
    condition = {'always': '战斗中', 'from_round': f"第{row['round']}轮起", 'at_round': f"仅第{row['round']}轮"}[row['condition']]
    operation = f"每轮回复{row['value']}%最大战斗态势" if row['effect'] == 'restore' else f"{effect}{row['value']}%" if row['effect'] == 'upkeep' else f"{effect}+{row['value']}%"
    return f"Lv.{row['level']} · 作为{SLOTS[row['slot']]}时，{condition}，{operation}。"


def validate_library(value):
    if not isinstance(value, dict) or set(value) - {'own', 'inherited', 'source_id', 'source_name', 'revision'}:
        raise ValueError('自创功法传承记录无效')
    for group in ('own', 'inherited'):
        books = value.get(group, {})
        if not isinstance(books, dict) or len(books) > 24:
            raise ValueError('每世最多二十四部自创传承')
        for key, row in books.items():
            if not isinstance(key, str) or not key.startswith(PREFIX) or len(key) > 100 or not isinstance(row, dict):
                raise ValueError('传承编号无效')
            book=row.get('technique')
            if not isinstance(book,dict) or book.get('id') != key:
                raise ValueError('传承编号不一致')
            integer(book.get('grade'),1,12,'功法境界')
            integer(book.get('level'),1,1,'传承原本等级')
            if not isinstance(book.get('name'),str) or not 2<=len(book['name'])<=24:
                raise ValueError('传承书名无效')
            for stat in STATS:
                n=book.get(stat)
                if type(n) not in (int,float) or not math.isfinite(n) or not 0<=n<=1e20:
                    raise ValueError('传承数值无效')
            if book.get('combat_interventions') or book.get('ignore_possession_limit') or book.get('doctrine_id') or book.get('spirit_voisinage_id'):
                raise ValueError('自创传承不能携带额外脚本或特殊身份')
            validate_buffs(book.get('authored_buffs', []))
            integer(row.get('cost'), 1, 10**9, '创法成本')
    if set(value.get('own',{})) & set(value.get('inherited',{})): raise ValueError('本世与前世传承编号重复')
    for key in ('source_id','source_name'):
        if key in value and (not isinstance(value[key],str) or len(value[key])>200): raise ValueError('传承来源无效')
    integer(value.get('revision', 0), 0, 10**9, '传承修订号')
    return value


def validate_insights(value):
    if not isinstance(value, dict) or set(value) - {'claimed', 'spent'}:
        raise ValueError('创法点数记录无效')
    claimed = value.get('claimed', {})
    if not isinstance(claimed, dict) or len(claimed) > 20000:
        raise ValueError('功法领悟记录无效')
    for key, amount in claimed.items():
        if not isinstance(key, str) or len(key) > 200:
            raise ValueError('领悟编号无效')
        integer(amount, 0, 10**9, '已领悟点数')
    integer(value.get('spent', 0), 0, 10**12, '已消耗点数')
    if value.get('spent', 0) > sum(claimed.values()):
        raise ValueError('创法点数支出超过收入')
    return value
