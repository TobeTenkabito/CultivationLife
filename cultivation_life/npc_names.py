"""Shared Chinese personal names for generated cultivators."""

SURNAMES = tuple("顾叶陆楚白谢云林江闻苏沈萧宁裴许温徐柳秦韩宋程周陈李赵王吴郑方杜薛孟夏钟唐季尹傅贺袁邵姚魏陶莫凌燕黎景苍月洛衡余段岳易叶穆关蓝池庄乔容殷商霍纪柏连卫施游俞")
GIVEN_NAMES = tuple("玄宁川微岳霜澄昭离砚青禾瑶岚珩昭瑜庭舟遥初澜霁晏澈蘅曜钧衡朔熙沅锦棠珏寻雪漪尘翎岑渊瑾泠宸衍安") + tuple(
    "玄真 清微 问岳 照霜 长离 守一 青崖 明河 玄川 清衡 玉微 长庚 云舒 听澜 怀瑾 知远 望舒 行舟 云岫 观澜 映雪 疏桐 凌霄 凝霜 怀砚 归尘 景初 临渊 昭月 衡秋 承渊 见微 霁川 语棠 知衡 望岳 清晏 道宁 玄度 霜华 松筠 飞白 逐光 星辞 庭玉 怀渊 归藏 若水 初晴 玄策 清辞 令仪 书珩 观星 岚汀 承霄 墨白 远山 映真 念慈 照夜 长风 玄岳 问天 清河 云笙 玄祯 拾月 净尘 含章".split()
)


def person_name(rng, used=()):
    occupied = set(used)
    for _ in range(64):
        name = rng.choice(SURNAMES) + rng.choice(GIVEN_NAMES)
        if name not in occupied:
            return name
    # Bounded deterministic fallback, without visible serial numbers.
    for surname in SURNAMES:
        for given in GIVEN_NAMES:
            if surname + given not in occupied:
                return surname + given
    raise ValueError("当前人物姓名池已用尽")
