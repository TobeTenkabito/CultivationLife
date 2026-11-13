"""Validate resumable fixed-book receipts, ownership, expiry and remaining budgets."""
import copy
import json
from ...technique_effect_schema import finite, integer
from ...combat_costs import technique_cost


def restore(runtime,value):
    fields={'version','round','started','ended','sequence','records','facts','observations','capacities','initial_state'}
    if not isinstance(value,dict) or set(value)!=fields or type(value['version']) is not int or value['version']!=1:
        raise ValueError('固定功法运行态结构无效')
    if len(json.dumps(value,allow_nan=False,ensure_ascii=False))>4000000:
        raise ValueError('固定功法运行态超过有限容量')
    round_no=integer(value['round'],0,1000000000,'续战轮次')
    for k in ('started','ended'):integer(value[k],0,round_no,'已执行轮次')
    sequence=integer(value['sequence'],0,1000000000,'回执序号')
    if value['capacities']!=runtime.capacities or value['initial_state']!=runtime.initial_state:
        raise ValueError('固定功法初始基准不得改写')
    records=value['records']
    if not isinstance(records,dict) or set(records)!=set(runtime.records):raise ValueError('固定功法续战来源不一致')
    for key,r in records.items():
        if not isinstance(r,dict) or set(r)!=set(runtime.records[key]):raise ValueError('固定功法收据字段无效')
        owner,b=runtime.books[key];e=b['effect'];cap=runtime.capacities[key]
        used=integer(r['used'],0,e['uses'],'使用次数')
        integer(r['last_cast'],0,round_no,'上次施展')
        integer(r['consumed'],0,sequence,'已用事件')
        integer(r['loss_seq'],0,sequence,'已用损耗')
        integer(r['forfeit_round'],0,round_no,'弃攻轮次')
        if type(r['forfeit_pending']) is not bool or type(r['reset']) is not bool:raise ValueError('转换标记无效')
        for k in ('rotation','completed'):integer(r[k],0,used,'成功兑现次数')
        integer(r['expired'],0,80,'过期计数')
        if r['field'] is not None:raise ValueError('固定功法不能保存外部领域状态')
        if not isinstance(r['receipts'],list) or len(r['receipts'])!=used:raise ValueError('固定功法付款回执缺失')
        expected=technique_cost(b,cap);eps=max(1e-8,expected*1e-10)
        finite(r['paid'],0,expected*used+eps,'整场实付')
        finite(r['refunded'],0,cap*.02+eps,'整场退款')
        totals=[0.,0.]
        for receipt in r['receipts']:
            if not isinstance(receipt,dict) or set(receipt)!={'paid','refunded','spent','success','round'}:raise ValueError('付款回执字段无效')
            finite(receipt['paid'],max(0.,expected-eps),expected+eps,'单次实付')
            finite(receipt['refunded'],0,min(receipt['paid']*.25,cap*.01)+eps,'单次退款')
            finite(receipt['spent'],0,1+1e-9,'单份预算消耗')
            integer(receipt['round'],1,round_no,'付款轮次')
            if type(receipt['success']) is not bool:raise ValueError('成功兑现标记无效')
            totals[0]+=receipt['paid'];totals[1]+=receipt['refunded']
        if any(abs(r[k]-total)>eps*max(1,used) for k,total in zip(('paid','refunded'),totals)):
            raise ValueError('固定功法付款总账不符')
        finite(r['refunded'],0,cap*.02+eps,'整场退款')
        if bool(used)!=bool(r['last_cast']) or used and r['last_cast']!=r['receipts'][-1]['round']:
            raise ValueError('施展次数与轮次不符')
        if r['completed']!=sum(x['success'] for x in r['receipts']):raise ValueError('成功兑现次数不符')
        packets=r['packets']
        if not isinstance(packets,list) or len(packets)>16:raise ValueError('固定功法分包过多')
        remaining=[receipt['spent'] for receipt in r['receipts']]
        for p in packets:
            names={'receipt','channel','share','initial_share','starts','expires','target','recipient','bound','first',
                   'wait_previous','burden','amount','basis','phase','applied','watch','seed','paused'}
            if not isinstance(p,dict) or set(p)!=names:raise ValueError('固定功法分包字段无效')
            index=integer(p['receipt'],0,used-1,'付款索引')
            channels={'strike','breach','sword','recover','shield','mobility','guard','response','cleanse',
                      'afterburn','arm_afterburn','followup','seed','choice_flame'}
            if p['channel'] not in channels:raise ValueError('未知固定功法分包')
            integer(p['paused'],0,1,'暂停次数')
            share=finite(p['share'],0,1,'剩余预算');finite(p['initial_share'],share,1,'初始分包预算')
            remaining[index]+=share
            at=r['receipts'][index]['round']
            integer(p['starts'],at,at+3,'分包起始');integer(p['expires'],p['starts'],at+3,'分包期限')
            if p['target'] not in runtime.battle.units or p['recipient'] not in runtime.battle.units:raise ValueError('分包原人物不存在')
            if runtime.battle.units[p['recipient']].unit.side!=runtime.battle.units[owner].unit.side:raise ValueError('不能把恢复给敌人')
            if runtime.battle.units[p['target']].unit.side==runtime.battle.units[owner].unit.side:raise ValueError('不能将队友当敌方事实来源')
            for k in ('bound','wait_previous','burden','applied','seed'):
                if type(p[k]) is not bool:raise ValueError('分包标记无效')
            if p['first'] is not None and type(p['first']) is not bool:raise ValueError('先后手记录无效')
            if p['watch'] is not None and (not isinstance(p['watch'],str) or len(p['watch'])>200):raise ValueError('来源记录无效')
            if p['phase'] not in {'','rebate','fragile','charged','shield_chain','sequential','resumed'}:raise ValueError('分包阶段无效')
            finite(p['basis'],0,1,'原始伤害基线')
            maximum=(runtime.support_amount(owner,p['recipient'],e['ward_bp']/10000*share) if p['channel'] in {'shield','recover'} else
                     p['basis']*runtime.strength(b)*share if p['channel']=='afterburn' else 0.)
            finite(p['amount'],0,maximum*(1+1e-9),'分包额度')
        if any(v>1+1e-9 for v in remaining):raise ValueError('分包超出一次实际付款预算')
        op=r['opportunity']
        if op is not None:
            if not isinstance(op,dict) or set(op)!={'at','expires','seq','target','first','source','kind','paused','loss_seq'}:raise ValueError('准备记录无效')
            integer(op['loss_seq'],0,sequence,'锁定损耗回执')
            integer(op['at'],1,round_no,'准备轮次');integer(op['expires'],op['at'],op['at']+3,'准备期限')
            integer(op['seq'],0,sequence,'准备回执');integer(op['paused'],0,1,'暂停次数')
            if op['target'] not in runtime.battle.units or op['kind'] not in {'opening','incoming','outgoing','cast'}:raise ValueError('准备来源无效')
            if op['first'] is not None and type(op['first']) is not bool:raise ValueError('准备先后手无效')
            if op['source'] is not None and (not isinstance(op['source'],str) or len(op['source'])>200):raise ValueError('准备招式来源无效')
    for k in ('facts','observations'):
        if not isinstance(value[k],dict) or set(value[k])!=set(runtime.battle.units):raise ValueError('专属功法观察归属无效')
        for owner,row in value[k].items():
            if not isinstance(row,dict) or len(row)>128:raise ValueError('专属功法观察超过容量')
    from .catalog_history import validate
    validate(runtime,value)
    for name in fields-{'version','capacities','initial_state'}:setattr(runtime,name,copy.deepcopy(value[name]))
    runtime.events=[];runtime.queue=[]
