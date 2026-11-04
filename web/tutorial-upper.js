/* Read-only upper-world curriculum. Loaded packages, never pending preferences. */
(() => {
  const worlds={celestial:'仙界',asura:'修罗界',reincarnation:'轮回界',nether:'幽冥界'};
  function build(config={},game=null,world=game?.player?.world){
    if(!Object.prototype.hasOwnProperty.call(worlds,world))return [];
    const loaded=new Set((config.extensions||[]).filter(e=>e.status==='loaded').map(e=>e.id));
    const on=id=>loaded.has('official.'+id), rows=[];
    const add=(title,text,panel)=>rows.push({title,text,panel});
    add(`${worlds[world]} · 先认清自己的路线`,'三级界面从第九阶起。来到这里并不自动获得本界道途、转化或传承；先核对人物详情的道途、境界与当前地点。此导览只查看，不代付资源、不触发突破。');
    if(world==='celestial'){
      add('第一步：仙元转化','先在「修行 → 仙元」查看仙灵力转化，按面板支付机缘逐段推进。单纯等待、读档或到达仙界不会完成转化。转化比例决定可用仙力，不能把它当作仙窍的当前储量。','immortal-conversion');
      add('第二步：开脉，再手动突破','仙界机缘是可花费的储量，不会攒满自动升层。每层先开三条仙脉，再手动突破；每境共二十七脉。开脉失败也耗资源并积累保底，小境界突破另有费用与成功率，先看当前报价。','immortal-veins');
      add('第三步：备功法与仙躯','从「经营 → 瑶池」取得仙界传承、专用仙躯功法与仙药。凡间炼体100层、完成转化后，按仙躯面板淬炼；普通炼体功法不能替代。仙躯10层是进阶金仙的条件之一，后续每10层解锁一色神光。','immortal-body');
      add('第四步：道统、邻域、仙窍','获得功法不等于领悟道统，领悟道统不等于已激发邻域。先取得注解并参悟道统，再激发、培养与上阵邻域；仙窍容量增加不会自动补满。出战前核对实际储量、维持费用和预案。','doctrine');
      add('第五步：准备跨境劫战','真仙、金仙、太乙跨大境界分别面对人五衰、天五衰、斩三尸；前两劫独自存活五轮，末劫须实际击杀三尸。备齐仙脉、仙躯等面板条件，恢复气血法力和仙窍后再入劫；续战保留损伤与消耗。','immortal-aperture');
    }else if(world==='asura'&&on('asura-manifestation')){
      add('第一步：启用修罗显圣的魔修','本次已加载「修罗显圣：无法无天」。修罗境魔修使用无上限机缘储量与专属修持；其它道途不会仅因身在修罗界获得八部。先在「修行 → 煞元」付机缘完成五重转化。','asura-conversion');
      add('第二步：魔躯与精魂','凡躯炼体100层后，以原面板培养魔躯。御傀中的已炼化元神可提纯为精魂；凝身使用真实俘虏或傀儡及其普通炼体条件。魔躯层数、普通炼体与对象修为是不同条件，先核对再支付。','asura-body');
      add('第三步：凝身入八部','按八部面板准备一至两具合格对象并挑战融合战，再培养本命与分支。八部2、4、7级开放各自权能，培养后还要在魔域中设置战前预案。选择与战斗均有真实代价，不是查看即获得。','asura-route');
      add('第四步：魔脉与突破','先贯通当前层需要的魔脉，再按突破入口备足机缘与资格。不要照搬仙界的仙痕、仙脉或人五衰条件；大境界按修罗专属劫战执行，以当前面板的条件、费用和胜负要求为准。','asura-veins');
      add('第五步：魔域、五蕴与备战','魔域、神通与魔躯五蕴各自培养，五蕴专材在修罗界取得。出战前核对煞元储量、魔域预案及实际可用权能；培养不等于回满资源，续战也不刷新消耗。','asura-domain');
    }else{
      const nether=world==='nether',ghost=world==='reincarnation';
      const specialized=nether?on('monster-bloodlines'):ghost?on('ghost-reincarnation'):false;
      if(nether&&specialized){
        add('第一步：血脉进化替代普通冲关','本次已加载「万妖归宗：血脉进化」。幽冥上境妖修仍从血脉面板选择进化，按节点积累机缘与满足前置条件，不能靠普通突破绕过进化。其它道途仍按自己的规则成长。','bloodline');
        add('第二步：确认祖路与本相','九阶妖修在幽冥界确认有效高阶血脉后，可在冥域预览并铭定本相。确认不赠等级和元力；主辅权能及后续调校会锁定，先阅读效果再选择。原九幽镇域、黄泉回生域仍可选。','upper-voisinage');
        add('第三步：妖躯五蜕','妖躯与普通百层炼体分开。妖躯每10层解锁一蜕，五项独修使用幽冥界专材；在「修行 → 妖躯」看费用、缺材与已解锁机制。培养仍须满足本人、地点及身体状态要求。','monster-body');
      }else if(ghost&&specialized){
        add('第一步：魂蚀与修行','本次已加载「百鬼夜行：往生轮回」。鬼修继续遵守魂蚀、往生与十魂规则；先核对魂基与魂体状态，再安排修炼。来到轮回界是跨界，主动轮回会放弃当前修为重来，两者不同。','ghost-soul');
        add('第二步：轮域与魂相','九阶鬼修可在轮域照前尘，参悟会消耗实际时间并结算魂蚀。守念、断执、化愿确认后锁定；蓝图确认不赠等级或元力，之后再按报价培养。六道劫域和两仪轮转域仍可选择。','upper-voisinage');
        add('第三步：鬼躯五法','在「修行 → 鬼躯」分别查看鬼躯层数与五法独修。每10层解锁一法，五种专材在轮回界取得；专材培养不能替代层数所需的普通筑域材料。寄身或神游时按真实身体资格限制。','ghost-body');
      }else{
        const label=nether?'万妖归宗':ghost?'百鬼夜行':'修罗显圣';
        add('第一步：本体普通上境路线',`本次未加载「${label}」。本界地图与普通修行仍可用，机缘到当前关口封顶后须手动突破；不要寻找未启用的${nether?'血脉进化、本相与妖躯':ghost?'十魂、魂相、鬼躯与轮回印记':'煞元、八部、魔脉与五蕴'}入口。`);
        add('第二步：按本界条件备功法','寻找本界、当前品阶的功法与材料，核对气等级、玉简和突破条件。本体普通炼体仍是百层体系；这三个上界不能照搬仙界的转化、仙脉与仙躯要求。');
      }
      add('培养本界邻域','三界本体邻域不依赖道途 DLC，不要求仙界道统、注解或仙痕。达到本界九阶后，在「修行 → 本界邻域」选择、修习并上阵，每场使用一种；初成、化境、大成各四层，之后至臻，进阶受人物境界限制。','upper-voisinage');
      add('跨境前，先看劫难与资源',specialized?'妖修与鬼修的九至十二阶跨境有三场专属劫战：前两劫存活五轮，末劫须实际击杀两名敌人。入劫前恢复气血法力、备足元力并检查上阵邻域；失败可能陨落，续战不会补满资源。':'普通上境仍按当前突破面板处理小关、大境界天劫与周期雷劫。资源不足先整备，不要因为机缘封顶便直接引劫；邻域培养和人物突破是独立操作。');
    }
    if(game?.player?.path==='confucian')add('当前道途：儒修',on('sage-way')?'圣人之道已加载，浩然与教化沿儒修面板处理；它不代替所在界面的突破条件。':'圣人之道未加载，使用本体修炼和飞升；不要求浩然、教化或外王专属资源。');
    if(game?.player?.path==='buddhist')add('当前道途：佛修',on('buddhist-dharma')?'诸法无我已加载，愿力、业力与弘法仍按佛修面板处理；不要因身处某一上界就套用其它道途的专属修持。':'诸法无我未加载，使用本体成长，没有愿力、涅槃和弘法加持要求。');
    add('遇到未开放入口怎么办','入口由当前人物、所在界面、身体状态与实际已加载 DLC 决定。异界访客、低阶角色或专属包未加载时，先阅读路线；不要反复点击隐藏入口。开关若提示待重启，本导览仍显示本次正在运行的规则。暂停后可从新手教程重看，真实费用始终以操作面板为准。');
    return rows;
  }
  function resolve(row){
    const entry=row.panel&&document.querySelector(`[data-panel-target="${row.panel}"]`);
    const available=entry&&!entry.matches('.hidden,.spatial-unavailable')&&!entry.disabled;
    return {title:row.title,text:row.text+(row.panel&&!available?' 当前人物尚未开放此入口，可先了解流程。':''),
      target:available?`#${row.panel}-card h2`:'#action-heading',context:available?row.panel:undefined,
      read:true,prepare:()=>{if(available)window.GameNavigation?.reveal(row.panel);}};
  }
  window.TutorialUpper={worlds,build,resolve};
})();
