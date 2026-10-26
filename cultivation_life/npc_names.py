"""Shared Chinese personal names for generated cultivators."""

SURNAMES = tuple("顾叶陆楚白谢云林江闻苏沈萧宁裴许温徐柳秦韩宋程周陈李赵王吴郑方杜薛孟夏钟唐季尹傅贺袁邵姚魏陶莫凌燕黎景苍月洛衡余段岳易叶穆关蓝池庄乔容殷商霍纪柏连卫施游俞")
GIVEN_NAMES = tuple("玄宁川微岳霜澄昭离砚青禾瑶岚珩昭瑜庭舟遥初澜霁晏澈蘅曜钧衡朔熙沅锦棠珏寻雪漪尘翎岑渊瑾泠宸衍安") + tuple(
    "玄真 清微 问岳 照霜 长离 守一 青崖 明河 玄川 清衡 玉微 长庚 云舒 听澜 怀瑾 知远 望舒 行舟 云岫 观澜 映雪 疏桐 凌霄 凝霜 怀砚 归尘 景初 临渊 昭月 衡秋 承渊 见微 霁川 语棠 知衡 望岳 清晏 道宁 玄度 霜华 松筠 飞白 逐光 星辞 庭玉 怀渊 归藏 若水 初晴 玄策 清辞 令仪 书珩 观星 岚汀 承霄 墨白 远山 映真 念慈 照夜 长风 玄岳 问天 清河 云笙 玄祯 拾月 净尘 含章".split()
)


SURNAMES = tuple(dict.fromkeys(SURNAMES + tuple("邢崔卢邱潘石任史贾邹熊康侯白孟汪龚汤严梅虞祝奚阮阙嵇祁倪卓褚闵辛聂荀晁詹蔺屠璩杭桑") + (
    "上官", "司徒", "司空", "欧阳", "诸葛", "慕容", "南宫", "端木", "公孙", "百里", "闻人", "澹台", "皇甫", "尉迟", "令狐", "钟离", "宇文", "长孙",
)))
GIVEN_NAMES = tuple(dict.fromkeys(GIVEN_NAMES + tuple(
    "怀玉 听雨 枕流 洗砚 照松 问竹 持衡 望津 含光 栖云 见山 照尘 归鹤 观复 闻溪 知白 守拙 抱朴 明夷 景行 如晦 雁回 疏影 晚照 孤鸿 寒汀 春汀 霜序 露白 澄心 映泉 星阑 云期 疏雨 听雪 栖梧 南枝 兰舟 清商 砚秋 汀兰 青蘅 令月 静姝 锦书 玉笙 月白 书凝 安歌 怀信 正则 灵均 嘉树 承宇 既明 昭华 辰良 修远 杜若 若华 予安 以宁 云归 如故 念初 星野 见素 玄同 太初 景和 承泽 砚池 知礼 明烛 载舟 牧川 临风 观海 白榆 归岑 照棠 静川 拂衣 宿雨 听枫 凌寒 望野 疏钟 寄舟 乘月 抱璞 清越 青岑 雪庭 鸣珂 忘机 采薇 月蘅 天霁 沧溟 映岚 知夏 逢春 秋水 微明 时雨 长策 照临 怀瑭 星垂 蘅芜 庭筠 扶光 含英 承露 思齐 敬之 允中 怀初 清芷 北辰 玄圭 韶华 苍梧 棠溪 瑞霖 定澜 飞琼 宜修 新桐 采蘩 松声 竹影 雪蘅".split()
)))


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
