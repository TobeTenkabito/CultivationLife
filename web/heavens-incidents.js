/* A single readable dossier at a time; actions share the existing preview flow. */
window.HeavensIncidents = (() => {
  const stages={unseen:'待求证',surveying:'求证中',surveyed:'待赴现场',treated:'待返程复核',closed:'已结案'};
  function render(host,row,ui,helpers){
    const {node,title,back,subview,renderActions}=helpers;
    back(host,'返回诸界','worlds');
    title(host,row.name,`${row.world_name} · ${stages[row.stage]}`);
    subview(host,[['record','见闻档案'],['response','现场事务'],['aftermath','后续影响']],'record',(body,section)=>{
      body.classList.add('heavens-incident');
      if(section==='record'){
        body.append(node('blockquote',row.glimpse,'heavens-finding'));
        const route=node('ol',null,'heavens-incident-route');route.setAttribute('aria-label','亲历路线');
        for(const [step,text] of [['壹',`${row.location_name} · 求证`],['贰',`${row.field_name} · 处理`],['叁',`${row.location_name} · 复核`]]){
          const stop=node('li');stop.append(node('span',step),node('strong',text));route.append(stop);
        }
        body.append(route,node('p',`参与需未封限的 ${row.rank} 阶以上修为。地点之间通过普通地图行走，行程另计。`));
        if(row.evidence){const article=node('article',null,'heavens-incident-document');article.append(node('small','已取得的证据'),node('p',row.evidence));body.append(article);}
        renderActions(body,row.actions.filter(a=>a.action==='incident_survey'));
      }else if(section==='response'){
        if(!row.evidence){body.append(node('p','先在起始地点核对旧记，取得本案依据后再选择处理方式。'));return;}
        if(row.finding){body.append(node('p',row.finding,'heavens-visit-finding'),node('small','处理分支已经确定；返回起始地点复核后结案。'));return;}
        body.append(node('p',`现场位于${row.field_name}。选择一项方案，先阅读投入与后果，再决定是否实施。`));
        const choices=row.actions.filter(a=>['incident_preserve','incident_seal'].includes(a.action));
        const select=node('select');select.setAttribute('aria-label','界域处理方案');
        for(const action of choices){const option=node('option',action.label);option.value=action.action;select.append(option);}
        const detail=node('article',null,'heavens-incident-document');
        const display=()=>{const selected=choices.find(a=>a.action===select.value);detail.replaceChildren();if(selected){detail.append(node('h4',selected.label),node('p',selected.description));renderActions(detail,[selected]);}};
        select.onchange=display;body.append(select,detail);display();
      }else{
        body.append(node('h4',row.stage==='closed'?'此案已留录':'复核与余响'));
        if(row.finding)body.append(node('p',row.finding));
        if(row.stage==='closed'){
          const balance=node('div',null,'heavens-incident-balance');balance.append(node('strong',`${row.remaining}`),node('span','年 · 可用当地余量'));body.append(balance);
          body.append(node('p','修行余量仅作用于当地普通修炼，累计额外所得不超过结案时境界基准的 2%；调息余量每年恢复 2% 气血。气血调理分支结案时恢复两成气血一次，满血不补发奖励。'));
        }else body.append(node('p',`完成现场处理后，亲自回到${row.location_name}复核。已耗年数和投入保留，处理不会自动传送人物。`));
        renderActions(body,row.actions.filter(a=>a.action==='incident_review'));
      }
    });
  }
  return {render};
})();
