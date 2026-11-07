"""Authored local inheritances; shared by scenery and the secret-art catalogue."""

STORIES = {
    'path_dao': dict(building='lake_mist', name='镜湖烟汀', location='mirror_lake',
        place='镜湖水府', title='不留倒影的石',
        opening='退潮露出一方刻石。石上记着一位散修舍去繁复法门、重整周天的经过，末行却被水痕遮住。',
        investigate='循水痕辨认周天图',
        discovery='你发现被抹去的不是口诀，而是各家气机的岔路。把岔路一一分清，中央那条返本的脉络便显现出来。石背提醒：归真不替人免除转修的损耗。',
        ending='你将返本的行气次序记入心中，领悟了返璞归真。湖面再起波纹，刻石仍留在原处。'),
    'path_confucian': dict(building='deer_echo', name='白鹿听雪坪', location='expanse_human_2',
        place='白鹿书山', title='雪下的一篇自省',
        opening='听雪坪旁的旧碑只剩半篇文章。前半尽述功名，后半却从一句“吾心何安”重新起笔。',
        investigate='对照两段文字的笔势',
        discovery='后半字迹不再争胜，句句指向立身与践言。你按文中次序梳理气息，读出了将杂念归于浩然的一套法门。碑末写着：有其法，还须自求经义。',
        ending='你默诵残篇，将养浩归儒的行气法记下。碑上的风雪没有被拂净，留待后来人继续读。'),
    'path_demonic': dict(building='broken_demon_stele', name='断誓残碑', location='skyfire_crater',
        place='天火陨坑', title='焚誓者留下的警句',
        description='陨坑外一块焦黑残碑被旧铁链环住，裂隙间仍能辨认几行戒语。',
        opening='碑上的名字被亲手凿去，只余一段由灵入魔的自述。末尾没有夸耀力量，而是反复告诫后来者先辨清魔气如何入脉。',
        investigate='按戒语辨认逆行脉络',
        discovery='你把逆行与暴走的两幅图分开，才看见化魔诀的完整次序。掌握它不代表立即入魔；没有魔道功法与足够魔气，转修仍将折损道基。',
        ending='你记下化魔诀，也记下碑文中的警戒。铁链纹丝未动，没有邪魂因此被释放。'),
    'path_ghost': dict(building='returning_soul_lamp', name='古渡留魂灯', location='frost_reed_marsh',
        place='寒芦泽', title='无名渡者的留灯诀',
        description='荒渡石龛里留着一盏不燃的石灯，灯座刻满沿水势回环的细纹。',
        opening='灯座小字记着一位肉身将尽的渡者。他没有求来另一具身体，只把如何收束散魂的尝试留在灯下。',
        investigate='循灯座细纹寻找归束之处',
        discovery='散开的纹路在灯心相合，收束后仍须以阴气温养。你辨出了阴魂续命诀；它不会凭空复生，也不能替代真正的鬼道功法。',
        ending='你将留魂之法记下。石灯没有亮起，渡者的旧事也没有被改写，但后来者多了一条可以自行选择的路。'),
    'path_buddhist': dict(building='silent_wheel_shrine', name='空山转轮龛', location='cangwu_mountains',
        place='苍梧群山', title='不向外求的一转',
        description='山径尽头只余一座风化石龛，龛前的石轮被历代过客磨得光滑。',
        opening='石轮转不动，龛内却刻着一句“先观转轮之心”。旁边几幅残图记述一位行者如何从旧法转入禅修。',
        investigate='静观残图中的呼吸次序',
        discovery='你不再用力推轮，转而辨清吐纳的起止。残图所授是转轮入禅的法门，既不替你求得佛门功法，也不许诺免去转修代价。',
        ending='你领会了转轮入禅，将法门默记。石龛仍是无主旧迹，没有因此变成你的寺院。'),
    'second_nascent': dict(building='twin_soul_pavilion', name='双影参玄台', location='border_void_watch',
        place='界门古塞', title='一灯双影的旧论',
        description='古塞背风处有一座残台，台心铜灯映出的两道刻影各自沿石纹延伸。',
        opening='台上残卷记载了两道元婴并存的推演。一道为本尊，一道须受持续同化；卷尾将失控的后果写得比所得更详。',
        investigate='辨认铜灯与双影刻痕',
        discovery='残卷分述本魂与第二元婴的边界，以及提炼、承载与同化三段法诀。须已凝成元婴，才能以自身感应领会其中关窍。取得传承不会造出元婴，仍须使用真实俘虏，逐年炼化并承担神魂耗损。',
        ending='你记下第二元婴秘法，将残卷归回台内。此后能否一身双魂，仍取决于你亲自准备与施术。'),
}


def acquisition_hint(identity):
    row = STORIES[identity]
    return f'人界 · {row["place"]} · {row["name"]}，探索「{row["title"]}」并领悟传承'


def scenery_seeds():
    return [dict(id=r['building'], name=r['name'], location_id=r['location'], description=r['description'])
            for r in STORIES.values() if 'description' in r]
