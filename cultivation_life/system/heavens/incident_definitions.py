"""Finite local incidents in the eleven ordinary worlds; no content imports."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Response:
    label: str
    years: int
    stones: int
    mana: float
    effect: str
    allowance: int
    finding: str


@dataclass(frozen=True, slots=True)
class Incident:
    id: str
    world: str
    world_name: str
    name: str
    location: str
    location_name: str
    field: str
    field_name: str
    rank: int
    survey_years: int
    glimpse: str
    evidence: str
    responses: tuple[Response, Response]
    category: str = 'local'


INCIDENTS = (
    Incident('human_beacon', 'human', '人界', '断烽归路', 'wudi_plain', '无棣原', 'lanjiang_steppe', '岚疆草原', 2, 2,
        '边道的旧烽标接连熄灭，沿途留下了相互矛盾的路引。先核对原上的旧驿簿，再亲赴草原处理。',
        '两批路引来自不同年代。旧界门的回声扰动了烽标，前哨正沿界门查探。',
        (Response('重校烽标', 4, 400, .03, 'practice', 12, '在草原重校了烽标。回到原上复核后，可借辨向所得辅助十二年的当地修行。'),
         Response('封存误导路引', 2, 80, 0, 'rest', 8, '误导路引封存，留下安全辨认法。复核后可在原上调息八年，逐年恢复额外气血。'))),
    Incident('spirit_thunder', 'spirit', '灵界', '雷汛借道', 'tianyuan_realm', '垂虹境', 'thunder_continent', '霆潮陆', 6, 4,
        '雷声自界外传来，一条废弃的接引支路上，又亮起了青白的电光。', '你循着焦痕查到霆潮陆。主脉的雷光平稳，只有旧支路的阵石烫得灼手。',
        (Response('疏导雷汛', 8, 2400, .12, 'practice', 24, '保留支路并疏导雷汛，留存完整相位观测，复核后用于二十四年本地参悟。'),
         Response('截断支路', 3, 600, .04, 'relief', 0, '截断支路后，雷声渐远。回去复核时，你可趁气息平稳调养一次气血。'))),
    Incident('demon_ash', 'demon', '魔界', '赤髓灰契', 'red_marrow_city', '赤髓城', 'corpse_refining_valley', '炼尸谷', 3, 3,
        '灰契上朱线朝东，谷口的香灰却一路往西飘。契尾还压着一枚褪色的军印。', '朱线记的是当年布阵的走向。如今阵脚已塌，散煞正顺着缺口往阵心流。',
        (Response('逐段封灰', 6, 700, .08, 'rest', 18, '残阵逐段封存，归城后用净息法调息十八年。'),
         Response('重录残阵', 9, 200, .15, 'practice', 20, '以较长时间和更多法力保存残阵变化，归城复核后辅助二十年修行。'))),
    Incident('true_demon_eclipse', 'true_demon', '真魔界', '黑日逆潮', 'black_sun_plain', '黑日原', 'abyss_city', '渊极城', 6, 5,
        '黑日阴影与渊城旧阵错位，逆潮沿失效阵线反复回流。', '错位来自两端阵线不同步，单独加固会把压力送回原处。',
        (Response('同步渊城阵线', 12, 3200, .15, 'practice', 32, '双端记录已经对齐，原上复核后留作三十二年逆潮参悟。'),
         Response('卸去阵线积压', 4, 1200, .05, 'relief', 0, '卸压后放弃旧线，归原复核时恢复自身两成气血。'))),
    Incident('monster_tracks', 'monster_realm', '妖界', '祖山错踪', 'myriad_beast_city', '万兽天城', 'ancestral_mountain', '祖兽山脉', 3, 2,
        '祖山通往旧界隙的兽径重叠，不同族群留下的足迹被错认作追兵。', '重叠足迹跨越多个季节，先辨生息，再决定保留还是封闭岔径。',
        (Response('重绘共行兽径', 7, 500, .05, 'practice', 16, '各族足迹分开标注，返城复核后形成十六年的生息参悟。'),
         Response('封闭失效岔径', 3, 150, .02, 'rest', 12, '封闭危险岔径，返城后可依安息法调息十二年。'))),
    Incident('phantom_dream', 'phantom_underworld', '幻冥界', '月原重梦', 'moonbeast_plain', '月兽原', 'nine_tail_dream_city', '九尾梦城', 6, 6,
        '月原上有人踏着月光往梦城走。你眨了眨眼，那人又回到刚才落脚的地方。', '你用袖口遮住旧印，月下的人影便停住了。移开衣袖，他又沿着同一串脚印走了一遍。',
        (Response('分辨三层梦印', 15, 1800, .10, 'practice', 36, '逐层保存梦印，返原复核后用于三十六年心神参悟。'),
         Response('唤醒沉滞梦印', 5, 800, .06, 'relief', 0, '放弃重演旧梦，返原复核时以清明法恢复自身两成气血。'))),
    Incident('hell_lantern', 'hell', '地狱界', '忘川失灯', 'ghost_gate', '幽关', 'soul_lantern_harbor', '魂灯渡', 3, 3,
        '渡口的引魂灯照向了岸后。守关人翻出旧灯簿，请你带去渡口，一盏盏对。', '灯簿翻到末页，多出来的那盏灯仍对不上名字。挑开灯罩，里面只剩一截冷透的旧芯。',
        (Response('续接引灯', 8, 900, .08, 'rest', 24, '你续上灯芯，渡口的石阶重新亮了起来。回关复核后，可用安魂息法调息二十四年。'),
         Response('摘除空灯', 4, 250, .03, 'practice', 12, '摘除没有名册依据的空灯，回关后把辨伪所得用于十二年修行。'))),
    Incident('celestial_seal', 'celestial', '仙界', '玉京缺诏', 'jade_capital', '玉京仙都', 'ascension_terrace', '登仙台', 9, 8,
        '登仙台旧封印缺失一角，玉京存录却有两份相反注解。', '你将两卷注解依年号排开。早年的拓本上，缺角处还有半笔朱痕，恰与后卷的收笔相合。',
        (Response('校订缺角封印', 20, 10000, .10, 'practice', 40, '按年代校订后归京复核，完整记录可用于四十年普通参悟。'),
         Response('暂封失校印面', 6, 2500, .04, 'rest', 20, '封住失校部分，归京后通过静息法获得二十年调息余量。'))),
    Incident('asura_banner', 'asura', '修罗界', '无生止战旗', 'ten_thousand_battle_city', '万战魔城', 'wusheng_battlefield', '无生战场', 9, 6,
        '无主战旗继续牵动旧阵余势，城中旧旗谱可以辨认其用途。', '你将旗脚压进土里，阵前的兵戈声也跟着低了下去。旧阵还认这面旗。',
        (Response('卸解战旗阵势', 12, 8000, .15, 'relief', 0, '卸去残余杀势，回城复核时恢复自身两成气血。'),
         Response('编录止战旗谱', 24, 3000, .08, 'practice', 36, '以较长勘录保存止战规律，回城后用于三十六年普通修行。'))),
    Incident('nether_roots', 'nether', '幽冥界', '太初断根', 'ancestral_beast_garden', '祖兽天苑', 'primal_chaos_wilds', '太荒幽域', 9, 10,
        '天苑的一支老根忽然断了生息。循根向下，断口一直延到太荒幽域。', '断根里面已经空了。你把手按在断口，一丝地气穿过掌心，远处的细根也随之一颤。',
        (Response('缓续地脉', 30, 9000, .12, 'practice', 48, '循生息缓续地脉，回苑复核后辅助四十八年的当地修行。'),
         Response('护住断根边缘', 8, 2200, .04, 'rest', 32, '保留断根边缘的安定区域，回苑后可调息三十二年。'))),
    Incident('reincarnation_ferry', 'reincarnation', '轮回界', '彼岸空渡', 'karma_city', '因果天城', 'other_shore_ferry', '彼岸渡', 9, 8,
        '彼岸旧渡契重复记载同一段行程，需要与城中因果旧录对照。', '你把两张渡契叠在灯前，船钱、指印，连右下角的墨点都分毫不差。原来是同一趟船被记了两回。',
        (Response('厘清空渡因果', 24, 7500, .10, 'practice', 40, '逐项厘清重复因果，回城复核后辅助四十年的普通参悟。'),
         Response('注销重记渡契', 6, 1800, .03, 'relief', 0, '注销重记，回城复核时安定心神，恢复自身两成气血。'))),
)
# Field anomalies and conflict relief have their own records, separate from the
# original local dossiers. They share the transactional fieldwork lifecycle.
REGIONAL_CONTENT = (
    ('落星失序', '星砂在夜间倒流，落点与观测时刻不再相合。', '星砂来自两段错开的地脉回声，稳定相位可取回散逸法力。', '校准星砂', '掩埋失序星眼',
     '岚疆伤驿', '烽线附近的旧伤驿缺少防护，行旅伤者只能在原地等待。', '核对伤驿名册并实地救护', '加固伤驿屏障'),
    ('雷海悬昼', '雷潮上方悬着不落的白昼，灵流持续向高处散逸。', '悬昼由雷脉与日光共振形成；可导回灵流，也可切断共振。', '引雷归脉', '断开悬昼回路',
     '霆潮补给线', '旧补给线被雷汛切断，驻地救治和避雷工事争用同一批物资。', '沿线设立救护点', '修复避雷工事'),
    ('灰谷逆影', '谷中影子逆着煞风移动，逐步侵蚀周围的法力。', '逆影依附废弃聚煞阵；顺势卸煞与封闭阵面需要不同投入。', '卸煞归元', '封闭逆影阵面',
     '赤髓停火驿', '昔日征伐留下的驿道仍有残阵，救护伤者前必须先辨明安全地带。', '开放停火救护处', '划定避战屏障'),
    ('渊底第二日', '深渊水面浮出另一轮黑日，吞纳附近的真魔气。', '第二日只是阵线折返的投影；折返气机仍可导回。', '导回渊底魔息', '沉封黑日投影',
     '渊城断营', '外营在逆潮中失去屏障，伤员转运与营地加固都需要亲临。', '救治断营伤者', '重设营地屏障'),
    ('祖山无声林', '林中万声消失，兽息却积聚在树冠上迟迟不散。', '古树共鸣困住了声音和灵息；疏通与静封可分别处理。', '疏通万兽灵息', '静封无声古树',
     '祖山共护道', '族群争道留下断裂护栏与伤者，共护道需要重新整理。', '救护沿途伤者', '重设共护界标'),
    ('梦城叠月', '醒时仍能看见两轮月亮，心神消耗被拖入梦影。', '两轮月来自不同梦层；循次醒梦能取回滞留灵息。', '循层醒梦', '隔断叠月梦层',
     '梦城醒伤所', '旧梦战场的余波困扰途经者，醒伤所和隔梦屏障均已失修。', '主持醒伤救护', '修复隔梦屏障'),
    ('忘川倒灯', '河面灯火朝水下燃烧，阴息被牵引到废灯座中。', '倒灯与废渡阵相连；疏引阴息或隔绝渡阵都能收束。', '疏引倒灯阴息', '隔绝废渡阵',
     '幽关安魂线', '关外争渡留下伤者与破损灯线，沿线还能听见伤者呼救。', '救护渡口伤者', '修补安魂灯线'),
    ('登仙台逆诏', '空中的诏纹逆向流转，仙息停滞在断裂的笔画之间。', '你沿断笔描了一遍，倒转的诏纹正好合拢。可循笔势引回仙息，也可封住断处。', '引回印间仙息', '封住逆诏断笔',
     '玉京护送簿', '旧护送通道尚未复原，地方伤者和沿途掩护都缺少照料。', '按实籍施行救护', '重整护送掩阵'),
    ('无生赤环', '战场上空浮出赤环，残留杀势吸走附近气机。', '阵心已空，赤环仍随旧阵转动。顺势卸环可收回气机，封住阵心则能隔开杀势。', '卸环归息', '隔离赤环阵心',
     '无生收伤阵', '旧战地的收伤阵破损，救治在场伤者与重设庇护只能择一投入。', '收治战地伤者', '重设止戈庇护'),
    ('太荒息壤潮', '息壤像潮水一样起伏，吞吐的灵息始终无法落地。', '断裂根脉与息壤相位相反；导通能回收灵息，固边则留下静息处。', '导通息壤灵脉', '固住息壤潮边',
     '天苑护生垒', '争夺地脉留下损坏的护生垒，巡途伤者缺少安置之处。', '救治护生垒伤者', '重筑护生垒'),
    ('彼岸回声轮', '渡头回声先于脚步传来，因果余息缠绕空转渡轮。', '回声轮仅错接了旧痕；解开顺序可归还灵息，封轮可止住余响。', '解开回声次序', '封止空转渡轮',
     '彼岸息兵渡', '争渡留下的掩阵和救护处俱损，停战后的安全仍需逐处维护。', '救治渡前伤者', '修复息兵掩阵'),
)


def _regional_cases():
    result = []
    for local, content in zip(INCIDENTS, REGIONAL_CONTENT):
        name, glimpse, evidence, recover, seal, war, situation, aid, shelter = content
        scale = local.rank
        common = dict(world=local.world, world_name=local.world_name, location=local.location,
                      location_name=local.location_name, field=local.field, field_name=local.field_name,
                      rank=local.rank, survey_years=local.survey_years)
        result.append(Incident(id=local.world+'_anomaly', name=name, glimpse=glimpse, evidence=evidence,
            category='anomaly', responses=(
                Response(recover, scale+2, scale*200, .12, 'mana', 0,
                         '灵流已经疏通。回去复核时，可借余息恢复一次法力，至多三成。'),
                Response(seal, max(2, scale//2), scale*80, .03, 'practice', scale*3,
                         f'封存异象并记录规律；返程复核后用于 {scale*3} 年当地普通参悟。')), **common))
        result.append(Incident(id=local.world+'_conflict', name=war, glimpse=situation,
            evidence='勘查已毕。可救治当地能接应的伤者，也可修起庇护工事，留作日后调息之处。',
            category='conflict', responses=(
                Response(aid, scale+1, scale*150, .08, 'aid', 0,
                         '可就地救治至多三名伤者，每人减轻一级伤势。'),
                Response(shelter, scale+3, scale*300, .04, 'rest', scale*4,
                         f'庇护工事完成；返程复核后可在起始地点调息 {scale*4} 年。')), **common))
    return tuple(result)


REGIONAL_CASES = _regional_cases()
ALL_INCIDENTS = INCIDENTS + REGIONAL_CASES
BY_ID = {row.id: row for row in ALL_INCIDENTS}
INCIDENT_IDS = frozenset(BY_ID)
INCIDENT_ACTIONS = frozenset({'incident_survey', 'incident_preserve', 'incident_seal', 'incident_review'})
LABELS = {'incident_survey': '核对本地旧记', 'incident_preserve': '保留并修复',
          'incident_seal': '隔离并收束', 'incident_review': '复核处理结果'}


def response(desc, action):
    return desc.responses[0 if action == 'incident_preserve' else 1]


def terms(desc, action):
    if action == 'incident_survey':
        return desc.survey_years, 0, 0
    if action == 'incident_review':
        return 2, 0, 0
    row = response(desc, action)
    return row.years, row.stones, row.mana
