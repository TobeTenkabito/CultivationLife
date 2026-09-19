const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
let config, game, busy = false, activeGroup = 'cultivation', activeView = 'cultivation';
async function api(path, options = {}) { const response=await fetch(path,{headers:{'Content-Type':'application/json'},...options}); const value=await response.json(); if(!response.ok)throw Error(value.error||'命令失败'); return value; }
function toast(text,kind=''){const node=$('#toast');node.textContent=text;node.className=`show ${kind}`;clearTimeout(toast.timer);toast.timer=setTimeout(()=>node.className='',2800);}

const GROUPS={
  cultivation:['修行','境界、功法、炼体、神识与变化之术','修'],world:['天地','地图旅行、跨界、飞升与全局设置','界'],
  relationships:['因果','道侣、道友、师徒、侍妾、家族与队伍','缘'],faction:['势力','宗门治理、外交、内政、战争与悬赏','宗'],
  economy:['营生','坊市、拍卖、黑市与物品交易','市'],production:['百艺','灵田、炼器、阵法与本命法宝','艺'],
  combat:['征伐','战斗、监狱、傀儡、炼魂与夺舍','斗'],dlc:['异道','鬼修、妖修与天庭扩展系统','异'],
};
const choice=(value,label)=>({value,label});
const textField=(name,label,source='',extra={})=>({name,label,type:'text',source,...extra});
const numberField=(name,label,extra={})=>({name,label,type:'number',...extra});
const selectField=(name,label,choices,extra={})=>({name,label,type:'select',choices,...extra});
const checkField=(name,label,extra={})=>({name,label,type:'check',...extra});
const multiField=(name,label,source,extra={})=>({name,label,type:'multi',source,...extra});
const op=(operation,group,label,description,fields=[],options={})=>({operation,group,label,description,fields,...options});
const YES_NO=[choice(true,'是'),choice(false,'否')];
const RELATION_KINDS=[choice('companion','双修道侣'),choice('friend','道友'),choice('master','师尊'),choice('disciple','弟子'),choice('concubine','侍妾')];
const CAPTURE_RELATION_KINDS=[choice('companion','双修道侣'),choice('friend','道友'),choice('master','师尊')];
const STATUS=[choice('alliance','同盟'),choice('truce','停战'),choice('neutral','中立'),choice('vassal','附庸'),choice('war','战争')];
const THIRD_STATUS=STATUS.filter(row=>row.value!=='war');

// 正式入口目录。operation 保持字面量，发布审计据此校验冻结的 V1 行为契约。
const OPERATIONS=[
  op('breakthrough','cultivation','冲击境界','尝试突破当前修行瓶颈。',[],{danger:true}),
  op('body-breakthrough','cultivation','炼体突破','尝试提升肉身层次。'),
  op('sense-breakthrough','cultivation','神识突破','尝试提升神识品阶。'),
  op('equip-technique','cultivation','装配功法','从已知功法中选择主修或辅助功法。',[textField('technique_id','功法','techniques',{required:true}),selectField('slot','功法位',[choice('main','主修'),choice('body','炼体'),choice('divine_sense','神识'),choice('transformation','变化')],{default:'main'})]),
  op('use-item','cultivation','使用物品','使用行囊中的可消耗物品。',[textField('item_id','物品','inventory',{required:true})]),
  op('alchemy','cultivation','开炉炼丹','选择目标丹药，并投入具体材料数量。',[textField('target_item_id','丹方或目标丹药','alchemyTargets',{required:true}),{name:'materials',label:'炼丹材料',type:'materials',required:true}]),
  op('transformation','cultivation','管理变化形态','收录、排序、激活或移除已经掌握的形态。',[textField('form_id','形态','forms',{required:true}),selectField('action','操作',[choice('store','收入变化位'),choice('activate','激活'),choice('deactivate','停用'),choice('promote','上移顺序'),choice('demote','下移顺序'),choice('remove','移除')],{default:'activate'})]),
  op('transformation-absorb','cultivation','直接吸收变化材料','将一件材料直接转化为变化之力。',[textField('item_id','材料','inventory',{required:true}),textField('stat_id','偏向属性','transformationStats')]),
  op('transformation-purify','cultivation','提纯变化材料','先提纯材料，再将其用于指定属性。',[textField('item_id','材料','inventory',{required:true}),textField('stat_id','偏向属性','transformationStats')]),
  op('transformation-batch','cultivation','批量吸收同类材料','一次处理背包中同类变化材料。',[textField('item_id','材料','inventory',{required:true}),selectField('mode','处理方式',[choice('direct','直接吸收'),choice('purified','提纯吸收')],{default:'direct'}),textField('stat_id','偏向属性','transformationStats')]),

  op('map-travel','world','地图旅行','前往当前世界内的其他地点。',[textField('destination_id','目的地','destinations',{required:true})]),
  op('cross-world','world','跨界旅行','通过既有通道前往其他世界。',[textField('destination','目标世界','worlds',{required:true})],{danger:true}),
  op('spirit-crossing','world','偷渡灵界','尝试避开正常飞升流程偷渡灵界；成功后解除服刑状态。',[],{danger:true}),
  op('celestial-ascension','world','飞升仙界','开始仙界飞升劫。',[],{danger:true}),
  op('asura-ascension','world','飞升修罗界','开始修罗界飞升劫。',[],{danger:true}),
  op('ascend-world','world','选择飞升世界','可邀请境界合适的道侣或道友同行。',[textField('destination_world_id','目标世界','worlds',{required:true}),multiField('invited_ids','邀请同行','ascensionInvites')],{danger:true}),
  op('settings','world','游戏设置','切换战斗弹窗、成就弹窗或玩家战争自动推进。',[selectField('setting','设置项',[choice('combat_popup','战斗结算弹窗'),choice('achievement_popup','成就解锁弹窗'),choice('auto_advance_player_wars','自动推进玩家战争')]),checkField('enabled','启用')]),
  op('debug-world-news','world','调试世界消息','Debug 模式下显示其他界面的世界消息。',[checkField('enabled','显示跨界消息')]),

  op('dao-companion','relationships','双修道侣','结为道侣，或与现有道侣互动。',[selectField('action','互动',[choice('propose','结为道侣'),choice('intimacy','亲密交谈'),choice('entwine','缠绵共参'),choice('request_item','索要物品'),choice('request_technique','索要功法'),choice('gift_item','赠送物品'),choice('teach_technique','传授功法')]),textField('npc_id','对象','npcs'),textField('content_id','物品或功法','giftContent')]),
  op('dao-friend','relationships','道友往来','结识新道友、切磋或交流心得。',[selectField('action','互动',[choice('befriend','结交'),choice('spar','点到切磋'),choice('discuss','交流心得')]),textField('npc_id','对象','npcs',{required:true})]),
  op('master-request','relationships','请教师尊','向师尊索要物品或请教功法。',[selectField('kind','请求内容',[choice('item','索要物品'),choice('technique','请教功法')])]),
  op('disciple-request','relationships','处理弟子请求','批准或驳回弟子提出的请求。',[textField('request_id','请求','discipleRequests',{required:true}),selectField('accept','决定',YES_NO,{cast:'boolean'})]),
  op('disciple-gift','relationships','赏赐弟子','向指定弟子赠送物品或功法。',[textField('disciple_id','弟子','disciples',{required:true}),selectField('kind','赏赐类别',[choice('item','物品'),choice('technique','功法')]),textField('content_id','赏赐内容','giftContent',{required:true})]),
  op('concubine-action','relationships','侍妾互动','招纳、使用炉鼎、炼尸或遣散侍妾。',[textField('target_id','对象','concubineTargets',{required:true}),selectField('action','操作',[choice('recruit','招纳侍妾'),choice('cauldron','当作炉鼎'),choice('corpse','炼为尸傀'),choice('dismiss','遣散')])]),
  op('concubine-status','relationships','侍妾身份','处理自己受高阶修士约束的侍妾身份。',[selectField('action','操作',[choice('escape','谋求脱身'),choice('depend','主动依附'),choice('request_technique','索要功法'),choice('request_stones','索要灵石'),choice('request_equipment','索要装备')]),selectField('method','脱身方式（仅脱身时）',[choice('covert','暗中逃离'),choice('plead','恳求脱身'),choice('abandon','自废修为')],{default:'covert'})]),
  op('relationship-capture','relationships','关系事件','尝试生擒一名关系人物。',[selectField('kind','关系类型',CAPTURE_RELATION_KINDS),textField('target_id','对象','npcs',{required:true})]),
  op('relationship-exit','relationships','结束关系','解除现有关系。',[selectField('kind','关系类型',RELATION_KINDS),textField('npc_id','对象','relationships',{required:true})],{danger:true}),
  op('relationship-faction','relationships','邀请关系人物入宗','邀请道侣、道友等加入当前势力。',[textField('npc_id','对象','relationships',{required:true})]),
  op('create-family','relationships','创建家族','建立属于自己的修真家族。',[textField('name','家族名','',{required:true,maxlength:20})]),
  op('party','relationships','队伍管理','邀请、离队、互动或调整飞升同行选择。',[textField('npc_id','人物','partyCandidates',{required:true}),selectField('action','操作',[choice('invite','邀请同行'),choice('leave','暂离队伍'),choice('interact','同行互动'),choice('crossing_add','加入飞升队伍'),choice('crossing_remove','移出飞升队伍')])]),

  op('create-faction','faction','创建宗门','建立新的修行势力。',[textField('name','宗门名','',{required:true,maxlength:20})]),
  op('leave-faction','faction','退出宗门','离开当前宗门并结算身份与贡献。',[],{danger:true}),
  op('faction-succession','faction','安排后事','飞升前将宗门控制权交付给继任者。',[],{danger:true}),
  op('faction-dispatch','faction','派遣门人','派遣宗门成员寻访物品或功法。',[selectField('target','寻访目标',[choice('item','物品'),choice('technique','功法')])]),
  op('faction-intercept','faction','拦截门人','拦截正在执行外务的宗门成员。',[textField('npc_id','门人','factionMembers',{required:true})]),
  op('faction-relationship','faction','建立师徒关系','从宗门名册中拜师或收徒。',[textField('npc_id','人物','factionMembers',{required:true}),selectField('role','关系',[choice('master','拜师'),choice('disciple','收徒')])]),
  op('faction-reward','faction','宗门赏赐','领取或指定一项宗门奖励。',[textField('reward_id','奖励','factionRewards',{required:true})]),
  op('faction-diplomacy','faction','宗门外交','改变与其他势力的外交立场。',[textField('target_id','目标势力','factions',{required:true}),selectField('status','关系',STATUS)]),
  op('race-diplomacy','faction','族群外交','改变与其他族群的外交立场。',[textField('target_id','目标族群','races',{required:true}),selectField('status','关系',STATUS)]),
  op('vassal-transfer','faction','附庸人员调动','从附庸宗门或族群调动人员。',[selectField('kind','势力类型',[choice('faction','宗门'),choice('race','族群')]),textField('target_id','目标势力','factions',{required:true}),textField('npc_id','人物','npcs',{required:true})]),
  op('intrigue-guest','faction','客卿事务','处理宗门或家族的客卿邀请与身份。',[selectField('kind','组织',[choice('sect','宗门'),choice('family','家族')]),selectField('action','操作',[choice('invite','邀请客卿'),choice('regularize','客卿转正'),choice('remove','撤销客卿'),choice('accept_invitation','接受外部邀请'),choice('decline_invitation','谢绝外部邀请'),choice('resign','辞去客卿')]),textField('npc_id','客卿或势力','npcs')]),
  op('intrigue-personnel','faction','人事任免','任命、奖惩、关押、释放或驱逐组织成员。',[selectField('kind','组织',[choice('sect','宗门'),choice('family','家族')]),selectField('action','操作',[choice('appoint','任命'),choice('dismiss','撤职'),choice('reward','赏赐'),choice('punish','惩罚'),choice('imprison','关押'),choice('release','释放'),choice('expel','逐出')]),textField('npc_id','成员','factionMembers',{required:true}),textField('position_id','职位','positions'),numberField('years','刑期（年）',{min:1,default:10}),textField('reason','事由')]),
  op('intrigue-recruitment','faction','招募大会','提出扩招决议，并从生成的候选人中正式录取。',[selectField('action','阶段',[choice('propose','提出扩招'),choice('confirm','确认录取')]),{name:'filters',label:'招募条件',type:'filters'},multiField('candidate_ids','候选人','recruitmentCandidates'),checkField('player_vote','玩家赞成',{default:true})]),
  op('intrigue-resolution','faction','议案表决','向宗门或家族提出正式议案。',[selectField('kind','组织',[choice('sect','宗门'),choice('family','家族')]),textField('resolution_type','议案类型','resolutionTypes',{required:true}),textField('target_id','议案对象','npcs'),checkField('player_vote','玩家赞成',{default:true})]),
  op('war-action','faction','战争行动','亲自参战、推进战局、征服、撤退或召集盟友。',[textField('war_id','战争','wars',{required:true}),selectField('action','行动',[choice('participate_round','亲自参加会战'),choice('round','推进一轮战争'),choice('conquest','执行征服'),choice('retreat','撤退'),choice('call_allies','召集盟友')]),textField('ally_id','盟友','factions')]),
  op('war-peace','faction','战争议和','提出停战、处决、结盟、附庸、赔款或兼并等条款。',[textField('war_id','战争','wars',{required:true}),selectField('term','条款',[choice('white_peace','无条件停战'),choice('execute','处决参战者'),choice('alliance','强制结盟'),choice('vassal','纳为附庸'),choice('change_relation','改变第三方关系'),choice('stones','灵石赔款'),choice('supplies','补给赔偿'),choice('dissolve','解散势力'),choice('annex','兼并势力')]),textField('target_id','人物目标','npcs'),textField('target_power_id','战败势力','factions'),textField('third_party_id','第三方','factions'),selectField('third_status','第三方关系',THIRD_STATUS,{default:'neutral'}),checkField('concede','我方让步')],{danger:true}),
  op('issue-bounty','faction','发布悬赏','以有权机构名义悬赏一名人物。',[textField('npc_id','目标人物','npcs',{required:true}),textField('authority','发布机构','bountyAuthorities',{required:true})]),

  op('market-refresh','economy','刷新坊市','刷新当前坊市货架。',[checkField('force','强制刷新')]),
  op('market-buy','economy','坊市购买','购买当前坊市中的物品。',[textField('offer_id','商品','marketOffers',{required:true})]),
  op('market-lock','economy','锁定商品','锁定或解除锁定坊市商品，刷新时予以保留。',[textField('offer_id','商品','marketOffers',{required:true})]),
  op('market-sell-plant','economy','出售灵植','将收获的灵植售予坊市。',[textField('item_id','灵植','inventory',{required:true})]),
  op('spirit-plant-use','economy','服用灵植','直接使用已经收获的灵植。',[textField('item_id','灵植','inventory',{required:true})]),
  op('auction-identity','economy','拍卖会身份','选择在本场拍卖会使用的化名。',[textField('alias','化名','auctionAliases',{required:true,maxlength:20})]),
  op('auction-consign','economy','拍卖寄售','寄售一件物品或资产并设定起拍价。',[textField('asset_id','寄售物','auctionAssets',{required:true}),numberField('start_price','起拍价',{min:0,default:0})]),
  op('auction-bid','economy','参与竞价','对当前拍品出价。',[textField('lot_id','拍品','auctionLots',{required:true})]),
  op('auction-advance','economy','推进拍卖','推进到下一轮竞价或结算。'),
  op('auction-negotiate','economy','拍卖会交涉','与会场中的修士进行私下交涉。',[textField('npc_id','交涉对象','auctionNpcs',{required:true})]),
  op('auction-private-buy','economy','私下购买','购买交涉对象给出的私下商品。',[textField('npc_id','卖家','auctionNpcs',{required:true}),textField('offer_id','报价','privateOffers',{required:true})]),
  op('auction-private-sell','economy','私下出售','向交涉对象出售资产。',[textField('npc_id','买家','auctionNpcs',{required:true}),textField('asset_id','资产','auctionAssets',{required:true})]),
  op('auction-private-bargain','economy','私下还价','对一项私下交易进行还价。',[textField('npc_id','交涉对象','auctionNpcs',{required:true}),selectField('side','交易方向',[choice('buy','购买'),choice('sell','出售')]),textField('asset_id','资产或报价','bargainAssets',{required:true})]),
  op('black-market-search','economy','探查黑市','使用线索或暗语寻找黑市。',[textField('pattern','线索或暗语','',{required:true})]),
  op('black-market-buy','economy','黑市购买','购买本次探查发现的商品。',[textField('result_id','商品','blackMarketResults',{required:true})]),
  op('black-market-sell','economy','黑市出售','将物品、资产或傀儡卖入黑市。',[selectField('kind','资产类型',[choice('item','物品或实例'),choice('puppet','傀儡')]),textField('asset_id','资产','blackMarketSellables',{required:true})]),
  op('black-market-leave','economy','离开黑市','结束本次黑市交易。'),

  op('spirit-field-reclaim','production','开垦灵田','瞬间开垦一块新灵田，不推进游戏时间。'),
  op('spirit-field-plant','production','播种灵田','在空闲田位种植灵植。',[textField('plant_id','灵植种类','plants',{required:true}),numberField('slot','田位',{min:0})]),
  op('spirit-field-irrigate','production','灌溉灵田','消耗法力灌溉指定田地，可加入增益材料。',[textField('plot_id','田地','plots',{required:true}),numberField('mp_ratio','法力比例',{min:0,max:1,step:0.05,default:0.25}),textField('booster_id','增益物品','inventory')]),
  op('spirit-field-harvest','production','收获灵田','收获已经成熟的灵植。',[textField('plot_id','田地','plots',{required:true})]),
  op('crafting-preview','production','预览炼器','选择胎模、四种不同材料并分配属性预算。',[textField('mold_id','胎模','craftingMolds',{required:true}),{name:'crafting',label:'炼器材料与属性',type:'crafting'}]),
  op('crafting-forge','production','正式炼器','按当前设计消耗材料并炼成法宝。',[textField('mold_id','胎模','craftingMolds',{required:true}),textField('name','法宝名','',{required:true,maxlength:20}),{name:'crafting',label:'炼器材料与属性',type:'crafting'}],{danger:true}),
  op('crafting-blueprint','production','保存炼器蓝图','保存当前炼器设计，供以后复用。',[textField('mold_id','胎模','craftingMolds',{required:true}),textField('blueprint_name','蓝图名','',{required:true,maxlength:20}),{name:'crafting',label:'炼器材料与属性',type:'crafting'}]),
  op('crafted-artifact','production','管理炼制法宝','设为本命、解除本命、出售或寄售成品法宝。',[textField('artifact_id','法宝','craftedArtifacts',{required:true}),selectField('action','操作',[choice('natal','炼为本命'),choice('unbind_natal','解除本命'),choice('sell','出售'),choice('consign','寄售')]),numberField('start_price','起拍价',{min:0,default:0})]),
  op('formation-preview','production','预览阵法','布置阵位并查看灵流、稳定度和效果。',[textField('name','阵法名','',{default:'无名阵',maxlength:20}),{name:'slots',label:'阵位',type:'formation'}]),
  op('formation-save','production','保存阵法','将当前阵位方案保存为阵法。',[textField('name','阵法名','',{required:true,default:'无名阵',maxlength:20}),textField('loadout_id','覆盖方案（可留空）','formations'),{name:'slots',label:'阵位',type:'formation'}]),
  op('formation-activate','production','激活阵法','激活一个已保存的阵法方案。',[textField('formation_id','阵法','formations',{required:true})]),
  op('formation-deactivate','production','停用阵法','停止当前激活的阵法。'),
  op('formation-delete','production','删除阵法','删除一个已保存的阵法方案。',[textField('formation_id','阵法','formations',{required:true})],{danger:true}),
  op('formation-ground-deploy','production','部署护山阵','为自己或当前宗门部署地面阵法。',[selectField('owner_kind','归属',[choice('player','个人'),choice('sect','宗门')])]),
  op('formation-ground-repair','production','修复护山阵','消耗阵法补给修复已部署阵法。',[textField('ground_formation_id','护山阵','groundFormations',{required:true}),textField('supply_id','补给','formationSupplies',{required:true}),numberField('quantity','数量',{min:1,default:1})]),
  op('formation-ground-withdraw','production','撤回护山阵','撤回一座已部署的地面阵法。',[textField('ground_formation_id','护山阵','groundFormations',{required:true})],{danger:true}),
  op('natal-artifact','production','本命法宝','认主、解除、温养或镶嵌本命法宝。',[selectField('action','操作',[choice('bind','炼为本命'),choice('unbind','解除本命'),choice('refine','温养祭炼'),choice('socket','镶嵌材料'),choice('unsocket','取回材料')]),textField('item_id','法宝或材料','assets'),numberField('slot_index','槽位',{min:-1,default:-1})]),

  op('fight','combat','发起战斗','选择目标与战斗目的。',[textField('target_id','对手','npcs',{required:true}),selectField('objective','目的',[choice('duel','切磋'),choice('kill','死斗'),choice('capture','擒获')])],{danger:true}),
  op('prison-action','combat','服刑行动','在监狱中忍耐、等待、修炼或越狱。',[selectField('action','行动',[choice('endure','忍耐服刑'),choice('wait','等待时机'),choice('cultivate','狱中修炼'),choice('escape','越狱')])]),
  op('captive-action','combat','俘虏处置','释放、拷问、炼尸、种傀印或夺舍俘虏。',[textField('target_id','俘虏','prisoners',{required:true}),selectField('action','处置',[choice('release','释放'),choice('torture','拷问'),choice('corpse','炼为尸傀'),choice('living','种下傀印'),choice('possess','夺舍')])],{danger:true}),
  op('craft-puppet','combat','炼制机械傀儡','按已掌握配方炼制一具机械傀儡。'),
  op('puppet-action','combat','傀儡管理','灌注、喂丹、传功、加固、吞噬或解除傀儡。',[textField('puppet_id','傀儡','puppets',{required:true}),selectField('action','操作',[choice('infuse','灌注灵气'),choice('pill','喂丹'),choice('technique','更换功法'),choice('reinforce_control','加固控制'),choice('devour','吞噬'),choice('dismiss','解除')]),textField('content_id','丹药或功法','inventory')]),
  op('refine-souls','combat','炼化异魂','炼化当前持有的异魂。',[],{danger:true}),
  op('secluded-refine-souls','combat','闭关炼魂','通过耗时闭关炼化异魂。',[],{danger:true}),
  op('post-battle-possession','combat','战后夺舍','对战败目标执行夺舍。',[textField('target_id','目标','npcs',{required:true})],{danger:true}),

  op('ghost-attachment','dlc','鬼修附物','附入一件寄魂物，或从当前器物中离开。',[selectField('action','操作',[choice('attach','附入器物'),choice('leave','离器')]),textField('item_id','寄魂物','inventory')]),
  op('ghost-constraint','dlc','鬼修制约','面对魂体制约时等待、抵抗或夺舍。',[selectField('action','操作',[choice('wait','等待'),choice('resist','抵抗'),choice('possess','夺舍')])]),
  op('ghost-leave-host','dlc','离开宿体','主动离开当前夺舍或附身的肉身。',[],{danger:true}),
  op('ghost-parade','dlc','百鬼夜行','参加夜行，与游魂结交、交锋或拘魂。',[selectField('action','操作',[choice('participate','参加夜行'),choice('befriend','结交'),choice('fight','交锋'),choice('capture','战而拘魂'),choice('bind','拘束败魂')]),textField('soul_id','魂魄','souls')]),
  op('ghost-reincarnation-prompt','dlc','准备转生','查看本次鬼修转生的条件与后果。'),
  op('ghost-reincarnate','dlc','鬼修转生','执行转生，结束当前鬼修形态。',[],{danger:true}),
  op('ghost-soul','dlc','魂魄管理','将拘魂装入魂位、卸下或永久放归。',[textField('soul_id','魂魄','souls',{required:true}),selectField('action','操作',[choice('equip','入魂位'),choice('unequip','卸下魂位'),choice('release','永久放归')]),textField('slot','魂位','ghostSlots')]),
  op('ghost-wangsheng','dlc','消耗往生','消耗一份或全部往生积累。',[checkField('all','消耗全部')]),
  op('monster-evolve','dlc','妖族进化','选择一条满足条件的血脉进化路线。',[textField('evolution_id','进化路线','evolutions',{required:true})],{danger:true}),
  op('custom-lineage-prepare','dlc','开启祖血铭刻','为自立血脉路线开启规则编辑器。',[textField('evolution_id','进化路线','evolutions',{required:true})]),
  op('custom-lineage-confirm','dlc','确认祖血规则','命名祖血并以结构化规则完成不可逆铭刻。',[textField('evolution_id','进化路线','evolutions',{required:true}),textField('name','祖血名','',{required:true,minlength:2,maxlength:16}),{name:'rules',label:'祖血规则',type:'lineageRules'}],{danger:true}),
  op('heavenly-court','dlc','天庭事务','参加考核，颁布决议或提请施行、废除天条。',[textField('action','行动','heavenlyActions',{required:true}),textField('target_id','对象','heavenlyTargets'),selectField('enact','是否颁行',[choice('','不改变'),choice(true,'颁行'),choice(false,'不颁行')],{cast:'nullableBoolean'}),numberField('influence_spend','消耗影响力',{min:0,default:0})]),
  op('heavenly-election','dlc','天庭选举','选择竞选策略，或承诺颁布决议与天条。',[selectField('method','方式',[choice('none','不追加策略'),choice('relationship','借助人脉'),choice('faction','调动宗门选票'),choice('promise_decree','承诺颁布决议'),choice('promise_law','承诺颁布天条')]),textField('pledge_id','承诺内容','heavenlyPromises')]),
];

function at(path,root=game){return String(path).split('.').reduce((value,key)=>value==null?undefined:value[key],root);}
function arrayAt(...paths){for(const path of paths){const value=at(path);if(Array.isArray(value))return value;}return [];}
function rowOption(row,fallback='id'){
  if(typeof row==='string')return{value:row,label:row};
  const value=row.value??row.id??row[`${fallback}_id`]??row.request_id??row.relation_id??row.definition_id??row.item_id??row.npc_id??row.name;
  const label=row.label??row.name??row.title??row.display_name??row.other?.name??value;
  const detail=row.quantity!=null?` ×${row.available??row.quantity}`:row.price!=null?` · ${row.price}灵石`:'';
  return value==null?null:{value:String(value),label:`${label}${detail}`};
}
function optionsFor(source){
  const relationships=arrayAt('relationships').map(row=>({...row,id:row.other?.id??row.npc_id??row.id,name:row.other?.name??row.name}));
  const inventory=arrayAt('inventory','inventory.items','inventory.stacks'),assets=arrayAt('assets.instances','assets');
  const maps={
    inventory,assets:[...inventory,...assets],giftContent:[...inventory,...arrayAt('player.cultivation.known_techniques')],alchemyMaterials:[...inventory.filter(row=>(row.tags||[]).includes('herb')&&!(row.tags||[]).includes('seed')),...arrayAt('crafting.materials').filter(row=>row.kind==='harvested_spirit_plant')],craftingMaterials:arrayAt('crafting.materials'),formationMaterials:arrayAt('formation_system.materials'),techniques:arrayAt('player.cultivation.known_techniques'),forms:arrayAt('player.transformations.forms'),transformationStats:[choice('might','威能'),choice('guard','防护'),choice('mobility','身法'),choice('sense','神识'),choice('sustain','续航'),choice('breach','破法')],
    destinations:arrayAt('world.destinations').filter(row=>row.accessible!==false),worlds:Object.entries(config?.worlds||{}).map(([id,name])=>({id,name})),relationships,
    npcs:[...relationships,...arrayAt('characters'),...arrayAt('party.candidates'),...arrayAt('intrigue_system.sections').flatMap(row=>row.members||[])],ascensionInvites:relationships.filter(row=>['dao_companion','dao_friend'].includes(row.kind)&&row.ascension_eligible===true),
    disciples:relationships.filter(row=>row.kind==='master_disciple'&&row.direction==='source'),discipleRequests:arrayAt('disciple_requests'),concubines:arrayAt('concubine_system.concubines').map(row=>({...row,id:row.id??row.npc_id})),concubineTargets:[...arrayAt('concubine_system.concubines'),...relationships,...arrayAt('party.candidates')],partyCandidates:[...arrayAt('party.candidates'),...arrayAt('party.members')],
    factionMembers:[...arrayAt('faction.roster','faction.members','family.roster'),...arrayAt('intrigue_system.sections').flatMap(row=>row.members||[])],factionRewards:Object.entries(at('faction.reward_options')||{}).map(([id,row])=>({id,...row})),factions:arrayAt('available_factions','governance.relations','faction.relations'),races:Object.entries(config?.races||{}).map(([id,name])=>({id,name})),positions:arrayAt('intrigue_system.sections').flatMap(row=>row.positions||[]),
    recruitmentCandidates:arrayAt('intrigue_system.sections').flatMap(row=>row.disciple_recruitment?.pending?.candidates||[]),resolutionTypes:Object.entries(at('intrigue_system.resolution_types')||{}).map(([id,name])=>({id,name})),wars:arrayAt('war_system.wars'),bountyAuthorities:arrayAt('war_system.bounty_authorities'),marketOffers:arrayAt('market.offers'),auctionLots:arrayAt('auction.lots'),auctionNpcs:arrayAt('auction.attendees'),auctionAliases:arrayAt('auction.player_aliases'),privateOffers:arrayAt('auction.attendees').flatMap(row=>row.trade_offers||[]),auctionAssets:arrayAt('auction.consignable_assets'),bargainAssets:[...arrayAt('auction.consignable_assets'),...arrayAt('auction.attendees').flatMap(row=>row.trade_offers||[])],blackMarketResults:arrayAt('auction.black_market_results'),blackMarketSellables:[...arrayAt('auction.consignable_assets'),...arrayAt('auction.black_market_sellable_puppets')],
    plots:arrayAt('production.plots'),plants:arrayAt('production.plants'),alchemyTargets:arrayAt('production.alchemy_targets'),craftingMolds:arrayAt('crafting.molds'),craftedArtifacts:arrayAt('crafting.artifacts'),formations:arrayAt('formation_system.loadouts'),groundFormations:arrayAt('formation_system.ground_arrays'),formationSupplies:arrayAt('formation_system.supplies'),
    prisoners:arrayAt('demonic_system.prisoners'),puppets:arrayAt('demonic_system.puppets'),souls:[...arrayAt('demonic_system.foreign_souls'),...arrayAt('ghost_system.bound_souls'),...arrayAt('ghost_system.parade.souls')],ghostSlots:arrayAt('ghost_system.slots'),evolutions:[...arrayAt('monster_system.candidates'),...(at('monster_system.custom_lineage_retroactive_available')?[{id:'__retroactive__',name:'补刻既有祖血'}]:[])],heavenlyActions:[choice('examination','接受进阶考核'),...arrayAt('heavenly_court.decrees').map(row=>choice(`decree:${row.id}`,row.name)),...arrayAt('heavenly_court.laws').map(row=>choice(`law:${row.id}`,row.name))],heavenlyTargets:arrayAt('heavenly_court.target_npcs'),heavenlyPromises:[...arrayAt('heavenly_court.decrees').map(row=>({id:row.id,name:`决议 · ${row.name}`})),...arrayAt('heavenly_court.laws').map(row=>({id:row.id,name:`天条 · ${row.name}`}))],
  };
  return(maps[source]||[]).map(rowOption).filter(Boolean).filter((row,index,rows)=>rows.findIndex(other=>other.value===row.value)===index);
}
const datalistId=(operation,name)=>`list-${operation}-${name}`.replace(/[^a-z0-9-]/gi,'-');
function renderField(field,operation){
  const id=`${operation}-${field.name}`,required=field.required?' required':'',value=field.default??'';
  if(field.type==='select')return`<label>${esc(field.label)}<select id="${id}" name="${esc(field.name)}" data-cast="${esc(field.cast||'')}"${required}>${field.choices.map(row=>`<option value="${esc(row.value)}"${String(row.value)===String(value)?' selected':''}>${esc(row.label)}</option>`).join('')}</select></label>`;
  if(field.type==='check')return`<label class="check"><input id="${id}" name="${esc(field.name)}" type="checkbox"${value?' checked':''}><span>${esc(field.label)}</span></label>`;
  if(field.type==='number'){const attrs=['min','max','step'].filter(key=>field[key]!=null).map(key=>` ${key}="${esc(field[key])}"`).join('');return`<label>${esc(field.label)}<input id="${id}" name="${esc(field.name)}" type="number" value="${esc(value)}"${attrs}${required}></label>`;}
  if(field.type==='multi'){const rows=optionsFor(field.source);return`<fieldset data-multi="${esc(field.name)}"><legend>${esc(field.label)}</legend><div class="option-grid">${rows.length?rows.map(row=>`<label class="check"><input type="checkbox" value="${esc(row.value)}"><span>${esc(row.label)}</span></label>`).join(''):'<span class="muted">当前没有可选对象</span>'}</div></fieldset>`;}
  if(field.type==='materials')return renderMaterials();if(field.type==='crafting')return renderCrafting();if(field.type==='formation')return renderFormation();if(field.type==='filters')return renderFilters();if(field.type==='lineageRules')return renderLineageRules();
  const rows=field.source?optionsFor(field.source):[],list=rows.length?`<datalist id="${datalistId(operation,field.name)}">${rows.map(row=>`<option value="${esc(row.value)}">${esc(row.label)}</option>`).join('')}</datalist>`:'';
  const attrs=['minlength','maxlength'].filter(key=>field[key]!=null).map(key=>` ${key}="${esc(field[key])}"`).join('');
  return`<label>${esc(field.label)}<input id="${id}" name="${esc(field.name)}" value="${esc(value)}"${rows.length?` list="${datalistId(operation,field.name)}"`:''}${attrs}${required}>${list}</label>`;
}
function renderMaterials(){const rows=optionsFor('alchemyMaterials');return`<fieldset class="wide materials"><legend>药材与数量</legend>${rows.length?rows.map(row=>`<div class="material-row"><label class="check"><input type="checkbox" data-material-id="${esc(row.value)}"><span>${esc(row.label)}</span></label><input type="number" min="1" value="1" aria-label="数量"></div>`).join(''):'<span class="muted">行囊中暂无可炼丹药材</span>'}</fieldset>`;}
const CRAFT_STATS=[['combat_power','威能'],['max_hp','气血'],['max_mp','法力'],['opportunity_efficiency','机缘效率'],['body_training_efficiency','炼体效率'],['divine_sense_efficiency','神识效率'],['tribulation_reduction','天劫减免'],['breakthrough_bonus','突破助益']];
function renderCrafting(){const assets=optionsFor('craftingMaterials');return`<fieldset class="wide"><legend>材料配置</legend><datalist id="craft-assets">${assets.map(row=>`<option value="${esc(row.value)}">${esc(row.label)}</option>`).join('')}</datalist><div class="subgrid">${[['primary_id','主材'],['secondary_a_id','辅材一'],['secondary_b_id','辅材二'],['quench_id','淬火材料']].map(([key,label])=>`<label>${label}<input data-craft-material="${key}" list="craft-assets" required></label>`).join('')}</div><div class="allocation-grid">${CRAFT_STATS.map(([key,label])=>`<label>${label}<input data-allocation="${key}" type="number" min="0" value="0"></label>`).join('')}</div></fieldset>`;}
function renderFormation(){const materials=optionsFor('formationMaterials');return`<fieldset class="wide"><legend>九宫阵位（至少两份可连通阵材）</legend><datalist id="formation-assets">${materials.map(row=>`<option value="${esc(row.value)}">${esc(row.label)}</option>`).join('')}</datalist><div class="formation-grid">${Array.from({length:9},(_,i)=>`<label>阵位 ${i+1}<input data-formation-slot="${i}" list="formation-assets"></label>`).join('')}</div></fieldset>`;}
function renderFilters(){
  const recruitment=arrayAt('intrigue_system.sections').map(row=>row.disciple_recruitment).find(Boolean)||{};
  const fields=[['spirit_root','灵根筛选','spirit_root_options'],['realm_index','修为筛选','realm_options'],['path','修炼功法','path_options'],['combat','战斗力筛选','combat_options'],['gender','性别筛选','gender_options']];
  return`<fieldset class="wide"><legend>候选条件</legend><div class="subgrid">${fields.map(([key,label,source])=>`<label>${label}<select data-filter="${key}">${(recruitment[source]||[]).map(row=>`<option value="${esc(row.id)}">${esc(row.name)}</option>`).join('')}</select></label>`).join('')}</div></fieldset>`;
}
function renderLineageRules(){
  const editor=at('monster_system.custom_lineage_editor')||{},components=editor.components||{},keys=[['phase','阶段'],['schedule','时机'],['condition','条件'],['target','目标'],['effect','效果']],count=Math.max(1,Number(editor.slots||1)),existing=editor.existing?.rules||[];
  const opts=key=>(components[`${key}s`]||components[key]||[]).map(rowOption).filter(Boolean);
  const values=Object.values(editor.values||{}).flat().map(rowOption).filter(Boolean).filter((row,index,rows)=>rows.findIndex(other=>other.value===row.value)===index);
  return`<fieldset class="wide lineage"><legend>祖血规则（功业点：${esc(editor.deeds?.total??'未知')}）</legend>${Array.from({length:count},(_,index)=>`<div class="rule-row" data-rule="${index}"><strong>规则 ${index+1}${index<existing.length?' · 已铭刻':''}</strong>${keys.map(([key,label])=>`<label>${label}<select data-rule-field="${key}"><option value="">请选择</option>${opts(key).map(row=>`<option value="${esc(row.value)}"${String(existing[index]?.[key]??'')===row.value?' selected':''}>${esc(row.label)}</option>`).join('')}</select></label>`).join('')}<label>数值<select data-rule-field="value"><option value="">请选择</option>${values.map(row=>`<option value="${esc(row.value)}"${String(existing[index]?.value??'')===row.value?' selected':''}>${esc(row.label)}</option>`).join('')}</select></label></div>`).join('')}</fieldset>`;
}
function operationAvailable(spec){if(game?.player?.alive===false)return false;if(game?.pending_event&&!['settings','debug-world-news'].includes(spec.operation))return false;if(at('demonic_system.imprisonment')&&!['prison-action','spirit-crossing','settings','debug-world-news'].includes(spec.operation))return false;if(spec.group==='dlc'){if(spec.operation.startsWith('ghost-'))return at('ghost_system.available')===true;if(spec.operation.startsWith('monster-')||spec.operation.startsWith('custom-lineage'))return at('monster_system.visible')===true&&at('monster_system.available')===true;if(spec.operation.startsWith('heavenly-'))return at('heavenly_court.visible')===true;}return true;}
function renderOperations(){
  const query=$('#operation-search').value.trim().toLowerCase(),rows=OPERATIONS.filter(spec=>(!query&&spec.group===activeGroup)||(query&&`${spec.label}${spec.description}${spec.operation}`.toLowerCase().includes(query))),group=GROUPS[activeGroup];
  $('#operation-title').textContent=query?'寻觅结果':group[0];$('#operation-summary').textContent=query?`找到 ${rows.length} 项可选事务`:`${group[1]} · 共 ${rows.length} 项`;
  $('#operation-list').innerHTML=rows.length?rows.map(spec=>{const available=operationAvailable(spec);return`<details class="operation-card" data-operation-card="${esc(spec.operation)}"><summary><span><strong>${esc(spec.label)}</strong><small>${esc(spec.description)}</small></span><span class="route-badge">${available?'可行':'条件未足'}</span></summary><form data-operation="${esc(spec.operation)}" class="operation-form">${spec.fields.map(field=>renderField(field,spec.operation)).join('')}<div class="submit-row"><button type="submit" class="${spec.danger?'danger':'primary'}"${available?'':' disabled'}>${spec.danger?'郑重决定':'执行'}</button></div></form></details>`;}).join(''):'<p class="empty-note">没有找到相符事务。</p>';
  document.querySelectorAll('.operation-form').forEach(form=>form.onsubmit=submitOperation);
}
function castValue(value,cast){if(cast==='boolean')return value==='true';if(cast==='nullableBoolean')return value===''?null:value==='true';return value;}
function collectPayload(form){
  const payload={};for(const element of form.elements){if(!element.name||element.type==='submit')continue;if(element.type==='checkbox')payload[element.name]=element.checked;else if(element.type==='number'){if(element.value!=='')payload[element.name]=Number(element.value);}else if(element.value!=='')payload[element.name]=castValue(element.value,element.dataset.cast);}
  form.querySelectorAll('[data-multi]').forEach(box=>payload[box.dataset.multi]=[...box.querySelectorAll('input:checked')].map(input=>input.value));
  if(form.querySelector('.materials'))payload.materials=[...form.querySelectorAll('[data-material-id]:checked')].map(input=>({item_id:input.dataset.materialId,quantity:Number(input.closest('.material-row').querySelector('input[type=number]').value)}));
  form.querySelectorAll('[data-craft-material]').forEach(input=>payload[input.dataset.craftMaterial]=input.value);
  if(form.querySelector('[data-allocation]'))payload.allocations=Object.fromEntries([...form.querySelectorAll('[data-allocation]')].map(input=>[input.dataset.allocation,Number(input.value)]));
  if(form.querySelector('[data-formation-slot]'))payload.slots=[...form.querySelectorAll('[data-formation-slot]')].map(input=>input.value||null);
  if(form.querySelector('[data-filter]'))payload.filters=Object.fromEntries([...form.querySelectorAll('[data-filter]')].filter(input=>input.value!=='').map(input=>[input.dataset.filter,input.type==='number'?Number(input.value):input.value]));
  if(form.querySelector('[data-rule]'))payload.rules=[...form.querySelectorAll('[data-rule]')].map(row=>Object.fromEntries([...row.querySelectorAll('[data-rule-field]')].filter(input=>input.value!=='').map(input=>[input.dataset.ruleField,input.type==='number'?Number(input.value):input.value]))).filter(row=>Object.keys(row).length);
  return payload;
}
function confirmOperation(spec){if(!spec?.danger)return Promise.resolve(true);return new Promise(resolve=>{const backdrop=$('#game-confirm-backdrop');$('#game-confirm-title').textContent=`确认${spec.label}`;$('#game-confirm-body').textContent='此举可能改变重要关系、资产或人物命途，是否继续？';backdrop.classList.remove('hidden');const finish=value=>{backdrop.classList.add('hidden');$('#game-confirm-accept').onclick=null;$('#game-confirm-cancel').onclick=null;resolve(value);};$('#game-confirm-accept').onclick=()=>finish(true);$('#game-confirm-cancel').onclick=()=>finish(false);});}
async function submitOperation(event){event.preventDefault();const form=event.currentTarget,spec=OPERATIONS.find(row=>row.operation===form.dataset.operation);if(!form.reportValidity()||!await confirmOperation(spec))return;await command(form.dataset.operation,collectPayload(form));}
async function command(operation,payload={}){
  if(busy||!game)return;busy=true;document.body.classList.add('busy');$('#save-state').textContent='正在推演…';
  try{const result=await api(`/api/games/${game.id}/${operation}`,{method:'POST',body:JSON.stringify(payload)}),next=result.game||result;game=next?.player?next:await api(`/api/games/${game.id}`);render();toast(result.events?.at?.(-1)?.message||'命令完成，存档已更新','success');}
  catch(error){toast(error.message,'error');}finally{busy=false;document.body.classList.remove('busy');$('#save-state').textContent='已保存';}
}
function fill(selector,rows){$(selector).innerHTML=Object.entries(rows||{}).map(([id,name])=>`<option value="${esc(id)}">${esc(name)}</option>`).join('');}
function renderSaves(){const node=$('#saves');node.innerHTML=(window.saves||[]).length?window.saves.map(row=>`<button data-id="${esc(row.game_id||row.id)}">续接 · ${esc(row.player_name||row.name)}</button>`).join(''):'<span class="muted">尚无存档</span>';node.querySelectorAll('button').forEach(button=>button.onclick=()=>load(button.dataset.id));}
async function load(id){game=await api(`/api/games/${id}`);render();}
function closePanels(){document.querySelectorAll('.utility-panel').forEach(panel=>panel.classList.remove('panel-open'));$('#system-nav').querySelectorAll('button').forEach(button=>button.classList.remove('active'));}
function openPanel(selector){closePanels();$(selector).classList.add('panel-open');}
function renderNav(){$('#system-nav').innerHTML=Object.entries(GROUPS).map(([id,[label,,glyph]])=>`<button type="button" data-group="${id}" title="${esc(label)}"><span>${esc(glyph)}</span><small>${esc(label)}</small></button>`).join('');$('#system-nav').querySelectorAll('button').forEach(button=>button.onclick=()=>{activeGroup=button.dataset.group;$('#operation-search').value='';renderOperations();openPanel('#operation-shell');button.classList.add('active');});}
const VIEWS={cultivation:['修行','player.cultivation'],world:['天地','world'],world_news:['世界消息','world_news'],relationships:['人物关系','relationships'],faction:['宗门','faction'],family:['家族','family'],intrigue_system:['内政','intrigue_system'],war_system:['战争','war_system'],inventory:['行囊','inventory'],production:['生产','production'],crafting:['炼器','crafting'],formation_system:['阵法','formation_system'],auction:['拍卖','auction'],market:['坊市','market'],combat:['战斗','combat'],party:['队伍','party'],demonic_system:['魔道','demonic_system'],ghost_system:['鬼修','ghost_system'],monster_system:['妖修','monster_system'],heavenly_court:['天庭','heavenly_court']};
function labelKey(key){const labels={id:'编号',name:'名称',status:'状态',available:'可用',visible:'可见',quantity:'数量',price:'价格',kind:'类别',role:'身份',current:'当前',active:'启用',members:'成员',offers:'商品',plots:'田地',wars:'战争',relations:'关系',world_name:'世界',location_name:'地点'};return labels[key]||String(key).replaceAll('_',' ');}
function renderValue(value,depth=0){if(value==null)return'<span class="muted">无</span>';if(typeof value==='boolean')return`<span class="pill ${value?'good':''}">${value?'是':'否'}</span>`;if(typeof value!=='object')return`<span>${esc(value)}</span>`;if(Array.isArray(value))return value.length?`<div class="state-list">${value.map(row=>`<article>${renderValue(row,depth+1)}</article>`).join('')}</div>`:'<span class="muted">暂无记录</span>';const entries=Object.entries(value).filter(([key])=>key!=='debug_world_news'||at('settings.debug_world_news')===true);return`<dl class="state-dl">${entries.map(([key,row])=>`<div><dt>${esc(labelKey(key))}</dt><dd>${depth>2&&typeof row==='object'?`<span class="muted">${Array.isArray(row)?`${row.length} 项`:'详情'}</span>`:renderValue(row,depth+1)}</dd></div>`).join('')}</dl>`;}
function showPanel(key){activeView=key;$('#view-tabs').querySelectorAll('button').forEach(button=>button.classList.toggle('active',button.dataset.view===key));$('#panel').innerHTML=renderValue(at(VIEWS[key]?.[1]||key));}
function renderViews(){$('#view-tabs').innerHTML=Object.entries(VIEWS).filter(([,row])=>at(row[1])!==undefined).map(([id,[label]])=>`<button type="button" data-view="${id}" class="${id===activeView?'active':''}">${esc(label)}</button>`).join('');$('#view-tabs').querySelectorAll('button').forEach(button=>button.onclick=()=>showPanel(button.dataset.view));if(!VIEWS[activeView]||at(VIEWS[activeView][1])===undefined)activeView='cultivation';showPanel(activeView);}
function renderStatus(){const flags=[['存活',game.player.alive!==false],['事件待决',Boolean(game.pending_event)],['服刑',Boolean(at('demonic_system.imprisonment'))],['宗门',Boolean(game.faction?.exists||game.faction?.id)],['家族',Boolean(game.family?.exists)],['拍卖会',['scheduled','open','black_market'].includes(game.auction?.status)]];$('#status-flags').innerHTML=flags.map(([label,on])=>`<span class="pill ${on?'good':''}">${esc(label)} · ${on?'是':'否'}</span>`).join('');}
function setMeter(name,current,total){const safeTotal=Math.max(1,Number(total)||1),safeCurrent=Math.max(0,Number(current)||0);$(`#${name}-text`).textContent=`${Math.round(safeCurrent)} / ${Math.round(safeTotal)}`;$(`#${name}-bar`).style.width=`${Math.min(100,safeCurrent/safeTotal*100)}%`;}
function renderChronicle(){const rows=[...(game.world_news||[]),...(game.story?.history||[])].slice(-8).reverse();$('#chronicle').innerHTML=rows.length?rows.map((row,index)=>{const year=row.year??row.at_year??game.clock.year,title=row.title||row.event_title||row.kind||'命途流转',body=row.message||row.summary||row.text||row.choice_text||'天地因果悄然变化。';return`<div class="record"><div class="year">${esc(year)}</div><div class="story"><h3>${esc(title)}</h3><p>${esc(body)}</p></div></div>`;}).join(''):`<div class="record"><div class="year">${esc(game.clock.year)}</div><div class="story"><h3>命途初启</h3><p>你的故事正从此刻开始。</p></div></div>`;}
function render(){
  $('#start').classList.add('hidden');$('#game').classList.remove('hidden');$('#new').classList.remove('hidden');$('#name').textContent=game.player.name;$('#avatar').textContent=game.player.name.slice(0,1);const c=game.player.cultivation;const realm=`${c.realm_name} · ${c.layer}层`;$('#realm').textContent=`${c.spirit_root_name} · ${c.path_name}`;$('#realm-display').textContent=realm;$('#age-line').textContent=game.player.lifespan==null?`${game.player.age} 岁 · 寿元无尽 · 纪年 ${game.clock.year}`:`${game.player.age} 岁 · 寿元 ${game.player.lifespan} · 纪年 ${game.clock.year}`;
  const combat=game.combat?.snapshot||{},hpMax=Number(combat.max_hp)||1,mpMax=Number(combat.max_mp)||1;setMeter('opportunity',c.opportunity,c.opportunity_required);setMeter('hp',hpMax*Number(combat.hp_ratio??1),hpMax);setMeter('mp',mpMax*Number(combat.mp_ratio??1),mpMax);
  $('#stats').innerHTML=[['战斗力',Math.round(combat.power||0)],['心魔',Math.round(c.heart_demon)],['世界',game.world.world_name||game.world.name],['地点',game.world.location_name||game.world.location?.name||'未知'],['炼体',game.player.body?.layer??0],['神识',game.player.divine_sense?.rank??0]].map(([key,value])=>`<div><dt>${esc(key)}</dt><dd>${esc(value)}</dd></div>`).join('');
  const units=Math.max(1,Number($('#action-units').value||1));$('#actions').innerHTML=Object.entries(config.actions||{}).map(([id,name])=>`<button data-action="${esc(id)}"><strong>${esc(name)}</strong><small>${units} 单位</small></button>`).join('');$('#actions').querySelectorAll('button').forEach(button=>button.onclick=()=>command('advance',{action:button.dataset.action,units:Math.max(1,Number($('#action-units').value||1))}));
  const event=game.pending_event;$('#event').classList.toggle('hidden',!event);if(event){$('#event-title').textContent=event.title;$('#event-body').textContent=event.body;$('#choices').innerHTML=(event.choices||[]).map(row=>`<button data-id="${esc(row.id)}" ${row.enabled?'':'disabled'}>${esc(row.text)}</button>`).join('');$('#choices').querySelectorAll('button').forEach(button=>button.onclick=()=>command('choice',{choice_id:button.dataset.id}));}
  renderNav();renderStatus();renderOperations();renderViews();renderChronicle();$('#save-state').textContent='已入因果录';
}
function fillWorlds(){const path=$('#paths').value,allowed=config.start_worlds?.[path]||['human'];$('#worlds').innerHTML=allowed.map(id=>`<option value="${esc(id)}">${esc(config.worlds?.[id]||id)}</option>`).join('');}
async function boot(){[config,{games:window.saves}]=await Promise.all([api('/api/config'),api('/api/games')]);fill('#roots',config.roots);fill('#paths',config.paths);fillWorlds();renderSaves();}
$('#operation-search').oninput=renderOperations;$('#action-units').onchange=()=>game&&render();$('#paths').onchange=fillWorlds;$('#operation-close').onclick=closePanels;$('#insight-close').onclick=closePanels;$('#insight-open').onclick=()=>openPanel('#insight-shell');document.addEventListener('keydown',event=>{if(event.key==='Escape')closePanels();});$('#new').onclick=()=>{closePanels();$('#game').classList.add('hidden');$('#start').classList.remove('hidden');$('#new').classList.add('hidden');};
$('#create').onsubmit=async event=>{event.preventDefault();const payload=Object.fromEntries(new FormData(event.target));if(!payload.seed)delete payload.seed;else payload.seed=Number(payload.seed);try{game=await api('/api/games',{method:'POST',body:JSON.stringify(payload)});render();}catch(error){toast(error.message,'error');}};
boot().catch(error=>toast(error.message,'error'));
