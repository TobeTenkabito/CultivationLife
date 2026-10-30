"""Complete book titles for the offline catalog authoring tool; no rank labels."""

# Images describe the required affinities, rather than an unrelated realm prefix.
IMAGES = {
    'metal': '白虹 秋锋 金霞 太白 灵锷 庚华 玉铓 霜刃 金关 铄石 锋潮 天钧'.split(),
    'wood': '青萝 碧梧 苍枝 玄藤 灵榕 古槐 玉枝 春芽 松涛 芳林 扶桑 建木'.split(),
    'water': '沧浪 清泓 寒汀 碧澜 澄波 玄泉 玉渊 秋潭 悬瀑 天池 星海 溟渤'.split(),
    'fire': '丹霞 赤烛 流焰 离照 朱薪 炎轮 烛天 阳燧 赤曜 焚星 燧皇 天炉'.split(),
    'earth': '黄壤 坤石 厚垣 岩心 玉嶂 玄砂 山骨 地髓 岳镇 坤轴 息壤 宸极'.split(),
    'wind': '清飙 流岚 天籁 碧飏 回飙 青吹 飞廉 灵籁 长飙 云翼 罡旋 天风'.split(),
    'thunder': '惊蛰 紫电 震鼓 霆光 雷池 灵霹 鸣霆 震枢 天鼓 殷雷 霆霓 震寰'.split(),
    'yin': '素月 寒魄 幽桂 玄阴 冷露 月华 阴璇 朔影 玉蟾 寒宫 太阴 夜璧'.split(),
    'yang': '晨曦 丹晖 旭轮 明燧 曜灵 朝暾 纯阳 日华 景曜 金乌 旸谷 羲和'.split(),
    'metal_water': '金津 霜涛 银瀑 剑泉 玉泓 寒铓 庚潮 锋澜 金渊 霜海 铄浪 天汞'.split(),
    'water_wood': '甘霖 雨棠 碧荷 润枝 沧藤 灵荇 青萍 涵芳 水榕 泽华 藏露 碧海'.split(),
    'wood_fire': '青灯 薪传 丹林 烛枝 焰蕊 朱梧 炎藤 燎原 火榕 丹桂 燧木 扶日'.split(),
    'fire_earth': '赤陶 熔岩 丹垣 炉岳 炎壤 赤砂 地焰 烬石 炽嶂 烛岳 熔髓 厚燧'.split(),
    'earth_metal': '砂锋 石铓 岳刃 金岫 岩锷 坤铄 玉铸 镇锋 地钧 藏金 金声 岳金'.split(),
    'wind_thunder': '风霆 飙电 震羽 巽鼓 迅雷 罡霹 雷翼 啸霆 飞电 风鼓 霆飙 巽震'.split(),
    'yin_yang': '两仪 晦明 素曜 日月 玄牝 阴阳 坎离 交泰 龙铅 虎汞 混融 太极'.split(),
    'wind_thunder_yin': '朔霆 寒飙 月电 幽霹 阴飓 霜霆 玄飙 冷雷 朔鼓 灵飓 冥霆 月罡'.split(),
    'wind_thunder_yang': '朝霆 曜飙 日电 炎飓 旸雷 赤飙 晓霆 羲电 丹罡 朱霹 旭飓 阳鼓'.split(),
    'wind_yin_yang': '晦风 明岚 玄籁 日巽 月巽 龙飙 虎飏 交飙 阴晴 灵晦 两曜 双飙'.split(),
    'thunder_yin_yang': '两霆 玄电 明雷 朔电 旭雷 龙霆 虎电 太枢 阴鼓 阳霹 晦电 双霆'.split(),
    'wind_thunder_yin_yang': '四灵 玄枢 晦霆 明飓 龙罡 虎霹 乾飙 坤雷 灵枢 四炁 交霆 天衡'.split(),
    'metal_water_wood': '玉露 碧锋 霜林 金蕖 雨锷 银藤 沧枝 泉铓 灵萍 青铄 露锋 三华'.split(),
    'wood_fire_earth': '赤榕 丹壤 青垣 炎枝 朱岳 烛林 灵薪 木髓 苍燧 芳嶂 燎岳 三光'.split(),
    'metal_wood_water_earth': '四序 山泽 川岳 碧嶂 玉沼 青钧 岩露 庚林 沧垣 金荇 涵岳 四庭'.split(),
    'wood_water_fire_earth': '四象 坤离 青冥 苍炉 泽燧 丹泽 灵畴 赤萍 碧壤 玉薪 水旸 四极'.split(),
    'five_elements': '五炁 五德 五岳 五藏 五轮 五华 五庭 五光 五运 五灵 五始 五元'.split(),
}
NEUTRAL_IMAGES = {
    'dao': '抱朴 守一 观妙 含章 归根 返景 澄怀 空明 玄圃 洞微 太素 道枢'.split(),
    'demonic': '烬心 血炉 冥烛 赤瞳 幽焰 锁魄 噬霞 魔胎 烬海 寂锋 玄煞 灭尘'.split(),
    'monster': '荒息 苍野 灵蜕 野渡 山魄 兽纹 洪泽 祖脉 万籁 龙庭 混茫 太荒'.split(),
    'ghost': '孤灯 冥息 魂汀 寒簧 残梦 九泉 晦烛 归墟 轮影 旧尘 返生 寂照'.split(),
}
CADENCES = {
    'dao': {
        'main': '养真经 存精诀 还元录 归藏篇 餐霞经 入微诀 澄心录 玄照篇 养炁经 抱一诀 会元录 守虚篇'.split(),
        'support': '护元录 养和篇 温脉经 承露诀 回生录 流照篇 涵元经 凝华诀 守静录 蕴灵篇 玉髓经 定光诀'.split(),
        'combat': '开锋诀 分光录 截流法 断尘篇 御虹诀 破云录 裁霞法 裂霄篇 碎岳诀 扫星录 荡日法 开天篇'.split(),
    },
    'demonic': {
        'main': '炼煞经 积玄典 饵灵篇 锻息录 餐晦经 藏锋典 逆照篇 养劫录 炼魄经 参寂典 合渊篇 纳冥录'.split(),
        'support': '护魄篇 封元录 缠脉典 蓄煞经 燃心篇 灵牢录 锁真典 护胎经 藏髓篇 归血录 镇魂典 续劫经'.split(),
        'combat': '夺锋诀 裂心书 噬影法 摧城录 斩念诀 焚野书 破狱法 戮星录 断劫诀 倾海书 诛曜法 绝尘录'.split(),
    },
    'monster': {
        'main': '吐息诀 纳灵经 抱元录 养纹篇 餐风诀 归脉经 蕴胎录 息海篇 涵荒诀 参野经 溯灵录 养宙篇'.split(),
        'support': '守魄经 护纹篇 温髓录 蓄精诀 养脉经 回灵篇 固本录 藏鳞诀 承元经 凝血篇 生华录 守藏诀'.split(),
        'combat': '裂石诀 逐电篇 踏岳书 截影法 崩霄诀 掀涛篇 攫月书 折星法 摧岭诀 吞日篇 撼天书 断界法'.split(),
    },
    'ghost': {
        'main': '养魂经 归寂录 炼息篇 观冥典 息念经 纳晦录 含魄篇 照尘典 返虚经 存影录 摄真篇 归幽典'.split(),
        'support': '安魂录 护念经 藏阴篇 涵魄法 凝露录 息灾经 缄神篇 续影法 养晦录 定魄经 温魂篇 守冥法'.split(),
        'combat': '摄魄诀 裁梦篇 摧魂录 绝影书 断缘诀 削念篇 裂魄录 斩业书 寂刃诀 破冥篇 断轮录 劫尘书'.split(),
    },
}


def technique_name(path, grade, family, role):
    """One affinity image and one coherent title, never prefix + reused book."""
    offset = {'dao':0, 'demonic':3, 'monster':6, 'ghost':9}[path]
    images = NEUTRAL_IMAGES[path] if family == 'neutral' else IMAGES[family]
    start = grade-1 if family == 'neutral' else (grade-1+offset) % 12
    cadence = CADENCES[path][role][grade-1]
    # Avoid tautologies such as 荒息吐息 or 澄怀澄心 in complete titles.
    for shift in range(len(images)):
        image = images[(start+shift) % len(images)]
        if not set(image) & set(cadence):
            return image + cadence
    raise ValueError(f'没有合适的功法书名意象：{path}/{grade}/{family}/{role}')
