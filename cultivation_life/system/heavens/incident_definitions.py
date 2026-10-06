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


INCIDENTS = (
    Incident('human_beacon', 'human', '人界', '断烽归路', 'wudi_plain', '无棣原', 'lanjiang_steppe', '岚疆草原', 2, 2,
        '边道的旧烽标接连熄灭，沿途留下了相互矛盾的路引。先核对原上的旧驿簿，再亲赴草原处理。',
        '两批路引来自不同年代。旧界门的回声扰动了烽标，不能据此认定眼前已有入侵军。',
        (Response('重校烽标', 4, 400, .03, 'practice', 12, '在草原重校了烽标。回到原上复核后，可借辨向所得辅助十二年的当地修行。'),
         Response('封存误导路引', 2, 80, 0, 'rest', 8, '误导路引封存，留下安全辨认法。复核后可在原上调息八年，逐年恢复额外气血。'))),
    Incident('spirit_thunder', 'spirit', '灵界', '雷汛借道', 'tianyuan_realm', '垂虹境', 'thunder_continent', '霆潮陆', 6, 4,
        '雷汛的界外余波进入旧接引支路；强行疏导和截断支路各有代价。', '实测确认主脉仍稳，过载只发生在霆潮陆的旧支路。',
        (Response('疏导雷汛', 8, 2400, .12, 'practice', 24, '保留支路并疏导雷汛，留存完整相位观测，复核后用于二十四年本地参悟。'),
         Response('截断支路', 3, 600, .04, 'relief', 0, '隔离支路，余下精力用于一次自身气血调理；不建立任何跨界运输许可。'))),
    Incident('demon_ash', 'demon', '魔界', '赤髓灰契', 'red_marrow_city', '赤髓城', 'corpse_refining_valley', '炼尸谷', 3, 3,
        '旧灰契所载的煞气流向与谷中实测不符。战时旧物不能当作新的征发命令。', '谷内残阵仍在吸纳散煞，灰契只是旧阵记录，没有现任宗门授权。',
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
        '梦城旧印在月原留下重影，回忆与当下气机需要分别验证。', '重梦是旧印投影，无法召回已死者，也不能复制仍活着的同道。',
        (Response('分辨三层梦印', 15, 1800, .10, 'practice', 36, '逐层保存梦印，返原复核后用于三十六年心神参悟。'),
         Response('唤醒沉滞梦印', 5, 800, .06, 'relief', 0, '放弃重演旧梦，返原复核时以清明法恢复自身两成气血。'))),
    Incident('hell_lantern', 'hell', '地狱界', '忘川失灯', 'ghost_gate', '幽关', 'soul_lantern_harbor', '魂灯渡', 3, 3,
        '渡口旧灯的引向紊乱。先查关前旧记，再到渡口辨认失效灯位。', '失灯没有对应新魂名册，不能凭空认领、复活或拘禁任何魂魄。',
        (Response('续接引灯', 8, 900, .08, 'rest', 24, '续灯只照明原渡口，回关复核后以安魂息法调息二十四年。'),
         Response('摘除空灯', 4, 250, .03, 'practice', 12, '摘除没有名册依据的空灯，回关后把辨伪所得用于十二年修行。'))),
    Incident('celestial_seal', 'celestial', '仙界', '玉京缺诏', 'jade_capital', '玉京仙都', 'ascension_terrace', '登仙台', 9, 8,
        '登仙台旧封印缺失一角，玉京存录却有两份相反注解。', '两份注解适用不同年份；修补旧印不能解释为新授天庭兵权。',
        (Response('校订缺角封印', 20, 10000, .10, 'practice', 40, '按年代校订后归京复核，完整记录可用于四十年普通参悟。'),
         Response('暂封失校印面', 6, 2500, .04, 'rest', 20, '封住失校部分，归京后通过静息法获得二十年调息余量。'))),
    Incident('asura_banner', 'asura', '修罗界', '无生止战旗', 'ten_thousand_battle_city', '万战魔城', 'wusheng_battlefield', '无生战场', 9, 6,
        '无主战旗继续牵动旧阵余势，城中旧旗谱可以辨认其用途。', '这是失去执旗者的阵势残留，没有可代为签署的军令主体。',
        (Response('卸解战旗阵势', 12, 8000, .15, 'relief', 0, '卸去残余杀势，回城复核时恢复自身两成气血。'),
         Response('编录止战旗谱', 24, 3000, .08, 'practice', 36, '以较长勘录保存止战规律，回城后用于三十六年普通修行。'))),
    Incident('nether_roots', 'nether', '幽冥界', '太初断根', 'ancestral_beast_garden', '祖兽天苑', 'primal_chaos_wilds', '太荒幽域', 9, 10,
        '混沌野的旧根脉与天苑生息分离，是否续接需要两地记录支持。', '断根已无现存生灵寄居，续接改变地脉，不会生成祖兽或血脉成果。',
        (Response('缓续地脉', 30, 9000, .12, 'practice', 48, '循生息缓续地脉，回苑复核后辅助四十八年的当地修行。'),
         Response('护住断根边缘', 8, 2200, .04, 'rest', 32, '保留断根边缘的安定区域，回苑后可调息三十二年。'))),
    Incident('reincarnation_ferry', 'reincarnation', '轮回界', '彼岸空渡', 'karma_city', '因果天城', 'other_shore_ferry', '彼岸渡', 9, 8,
        '彼岸旧渡契重复记载同一段行程，需要与城中因果旧录对照。', '重复的是记录而非生命；更正渡契不能倒流时间或返还往年消耗。',
        (Response('厘清空渡因果', 24, 7500, .10, 'practice', 40, '逐项厘清重复因果，回城复核后辅助四十年的普通参悟。'),
         Response('注销重记渡契', 6, 1800, .03, 'relief', 0, '注销重记，回城复核时安定心神，恢复自身两成气血。'))),
)
BY_ID = {row.id: row for row in INCIDENTS}
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
