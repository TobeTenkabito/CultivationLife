/* A replayable tour of existing views. It never submits a game command. */
(() => {
  const $=s=>document.querySelector(s);
  const compact=()=>!!window.GameNavigation?.isCompact();
  const pixel=()=>document.documentElement.dataset.visual==='pixel';
  const opened=name=>!!$(`#${name}-card`)?.classList.contains('panel-open');
  const reveal=name=>window.GameNavigation?.reveal(name);
  const panel=(name,title,text)=>({target:`[data-panel-target="${name}"]`,title,text,click:true,prepare:()=>reveal(name),complete:()=>opened(name)});
  const close=name=>({target:`#${name}-toggle`,context:name,title:'回到主界面',text:'请点击高亮的“关闭”，返回主界面。关闭窗口不会离开当前地点。',click:true,complete:()=>!opened(name)});
  function resolve(key){
    const mobile=compact();
    const steps={
      ui_welcome:{target:'#action-heading',title:'先认路，再问道',text:'这份导览带你认识当前界面的入口。只查看面板、切换栏目和查找功能，不修炼、不旅行，也不领取教学奖励。随时可暂停，之后从新手教程继续。',read:true},
      ui_identity:{target:'.hud-identity, .composition-details',title:'人物入口在这里',text:'请点人物铭牌。境界、寿元和常用资源集中在这里，详细属性、功法与衣橱在人物详情中。',click:true,complete:()=>$('#player-details-dialog').open},
      ui_details:{target:'#root-efficiency',context:'details',title:'详情里找功法与成长',text:'这里可以核对资质、功法配置、炼体和神识。学会功法之后还需要配置；人物外观可从立绘旁的衣橱入口调整。',read:true},
      ui_close_identity:{target:'[data-close-dialog="player-details-dialog"]',context:'details',title:'返回主界面',text:'请关闭人物详情。接下来认识主界面的行动分类。',click:true,complete:()=>!$('#player-details-dialog').open},
      ui_actions:{target:'.action-tabs',title:'行动分成三栏',text:'日常修行、历练与生计、斗法与狩猎各有一栏。旁边的行动单位影响实际耗时；普通行动可能推进多年，按下前先看费用、时间和条件。',read:true},
      ui_living:{target:'#tab-living',title:'切换到历练与生计',text:'请点这一栏。寻幽探宝、坊市委托与下山游历都在这里；本次只切换栏目。',click:true,complete:()=>$('#action-card').dataset.selectedCategory==='living'},
      ui_daily:{target:'#tab-daily',title:'回到日常修行',text:'请切回“日常修行”。接下来只认识入口，无须按下修炼或突破按钮。',click:true,complete:()=>$('#action-card').dataset.selectedCategory==='daily'},
      ui_scenery:{target:pixel()?'#pixel-place-name':'#player-hud',title:pixel()?'绘景和地点信息':'当前位置与状态',text:pixel()?(mobile?'手机将绘景收在页首“展开山海绘景”按钮中。这里展示当前地点、天地气息与当地建筑；查看绘景不会移动。':'山海绘景展示当前地点、天地气息和当地建筑。“行程与势力”可打开地图；查看绘景不会移动。'):'页首显示人物和常用状态。设置中可开启新版界面；导览会按你当前使用的布局指引入口。',read:true,
        prepare:()=>{if(pixel()&&compact()){const button=$('#pixel-scenery-toggle');if(button&&!button.hidden&&!button.disabled&&!$('#pixel-scenery-drawer').open)button.click();}}},
      ui_navigation:{target:mobile?'#navigation-bar':'.left-dock',title:mobile?'六个分类，不必满屏找按钮':'侧栏单字就是功能入口',text:mobile?'底栏依次是常用、修行、百艺、经营、同道、诸界。点分类展开目录，搜索会查找全部已开放功能。':'左右侧栏放置功能入口。鼠标悬停或键盘聚焦可看全名；左侧有行囊等常用功能，右侧有宗门、地图等。设置中可以让名称始终显示。',read:true},
      ui_directory:mobile?{target:'[data-navigation-category="craft"]',title:'亲手打开一个分类',text:'请点底栏“百艺”。我们从这里找到行囊。',click:true,complete:()=>GameNavigation.isOpen()}:
        panel('inventory','亲手打开行囊','请点左侧“行囊”。同一个入口始终打开原来的行囊窗口。'),
      ui_search:mobile?{target:'#navigation-search',title:'找不到时，搜名字',text:'请在搜索框输入“行囊”。搜索覆盖所有已开放分类；未解锁的功能不会被搜索提前开放。',input:true,prepare:()=>{if(!GameNavigation.isOpen())GameNavigation.open('craft');},complete:()=>$('#navigation-search').value.trim()==='行囊'}:
        {target:'#inventory-card h2',context:'inventory',title:'打开后再看细分内容',text:'行囊窗口内按原栏目查看物品与用途。桌面侧栏可直接打开，手机则通过底栏分类进入。',read:true},
      ui_inventory:mobile?{target:'[data-panel-target="inventory"]',title:'从搜索结果打开',text:'请点搜索结果中的“行囊”。功能旁的星标可以加入“常用”，最多八项；不想改常用列表，可以保留原样。',click:true,prepare:()=>{if(!GameNavigation.isOpen())GameNavigation.reveal('inventory');},complete:()=>opened('inventory')}:
        {target:'#inventory-card h2',context:'inventory',title:'行囊与物品',text:'资源、装备与玉简都有各自用途。这里只认识窗口；需要配置主修时，请回人物详情查看已悟功法。',read:true},
      ui_close_inventory:close('inventory'),
      ui_map:panel('map','远行前先打开地图',mobile?'“诸界”分类里有地图。请点高亮入口，查看当前位置与路线。':'请点右侧“地图”。在这里查看当前位置、路线和势力信息。'),
      ui_roads:{target:'#map-current',context:'map',title:'看地图不等于走过去',text:'当前地点显示在这里。地图内可切换名录和可视页面；真正行路需要另选路线并承担耗时与条件。本次不用选择目的地。',read:true},
      ui_close_map:close('map'),
      ui_heavens:panel('heavens','诸天玩法也有统一入口',mobile?'“诸界”中还有“诸天”。请打开它，认识见闻、行程与开拓入口。':'请打开侧栏的“诸天”，认识见闻、行程与开拓入口。'),
      ui_heavens_info:{target:'#heavens-card h2',context:'heavens',title:'见闻、行程与跨界开拓',text:'诸天窗口按栏目整理情报与玩法；“诸界”栏目中可查看跨界开拓。看见入口不代表已有通行资格，正式行动仍检查当前身份、地点、经费和路线。',read:true},
      ui_close_heavens:close('heavens'),
      ui_settings:panel('settings','设置与帮助都在这里',mobile?'请从“常用”目录打开“设置”。主题、存档和教程都能在这里找到。':'请点设置入口。主题、存档和教程都能在这里找到。'),
      ui_appearance:{target:'#settings-card .settings-appearance h3',context:'settings',title:'新版配色与侧栏名称',text:'界面主题、新版界面开关、浅暗配色和侧栏名称显示都在这一带。导览不会替你改偏好，之后可以按自己的习惯调整。',read:true},
      ui_save:{target:'.settings-save-transfer h3',context:'settings',title:'自动保存，也可以随身带走',text:'进度会自动保存。这里可导出当前存档，或导入另一份存档；导出码用于备份与跨设备续玩。本次无需导入或覆盖任何存档。',read:true},
      ui_handbook:{target:'#tutorial-handbook summary',title:'忘记规则时查百科',text:'请展开一篇修行指南。上方还可按关键词和分类检索；内容会结合当前已加载的玩法显示。',context:'settings',click:true,complete:hit=>hit.parentNode.open},
      ui_finish:{target:'#setting-tutorial-open',context:'settings',title:'现在知道去哪里找了',text:'以后仍可从“新手教程 → 新版界面导览”重新认识入口。想亲手试一遍修炼、探宝、拜师与入门，再选择“修行实践引导”。',read:true},
    };
    return steps[key];
  }
  const keys=['ui_welcome','ui_identity','ui_details','ui_close_identity','ui_actions','ui_living','ui_daily','ui_scenery','ui_navigation','ui_directory','ui_search','ui_inventory','ui_close_inventory','ui_map','ui_roads','ui_close_map','ui_heavens','ui_heavens_info','ui_close_heavens','ui_settings','ui_appearance','ui_save','ui_handbook','ui_finish'];
  window.TutorialInterface={resolve,keys:()=>{const entry=$('[data-panel-target="heavens"]');return keys.filter(key=>!key.includes('heavens')||entry&&!entry.matches('.hidden,.spatial-unavailable'));}};
})();
