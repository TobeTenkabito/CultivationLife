import json, math, random, networkx as nx
m=json.load(open('content/maps.json',encoding='utf8'));out={}
def cross(a,b,c,d):
 def det(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
 return det(a,b,c)*det(a,b,d)<-1e-5 and det(c,d,a)*det(c,d,b)<-1e-5
def crossings(pos,edges):
 return sum(cross(pos[a],pos[b],pos[c],pos[d]) for i,(a,b) in enumerate(edges) for c,d in edges[i+1:] if len({a,b,c,d})==4)
def normalize(p):
 xs=[float(v[0]) for v in p.values()];ys=[float(v[1]) for v in p.values()]
 return {k:[80+(float(v[0])-min(xs))/max(.01,max(xs)-min(xs))*840,70+(float(v[1])-min(ys))/max(.01,max(ys)-min(ys))*560] for k,v in p.items()}
def cost(p,edges):
 pts=list(p.values());score=0
 for i,a in enumerate(pts):
  for b in pts[i+1:]:
   dx,dy=abs(a[0]-b[0]),abs(a[1]-b[1]);score+=max(0,110-dx)*max(0,95-dy)*10+20000/max(20,math.dist(a,b))
 for a,b in edges:score+=math.dist(p[a],p[b])*.08
 return score
for w,d in m['worlds'].items():
 g=nx.Graph();g.add_nodes_from(n['id'] for n in d['locations']);portals=[]
 for r in d['routes']:
  a,b=r['from'],r['to'];g.add_edge(a,b)
  if not nx.check_planarity(g)[0]:g.remove_edge(a,b);portals.append([a,b])
 edges=list(g.edges);best=normalize(nx.planar_layout(g));score=cost(best,edges)+crossings(best,edges)*5000
 for seed in range(90):
  p=normalize(nx.spring_layout(g,seed=seed,iterations=200))
  candidate=cost(p,edges)+crossings(p,edges)*5000
  if candidate<score:best,score=p,candidate
 while crossings(best,edges):
  counts={e:0 for e in edges}
  for i,e in enumerate(edges):
   for f in edges[i+1:]:
    if len(set(e+f))==4 and cross(best[e[0]],best[e[1]],best[f[0]],best[f[1]]):counts[e]+=1;counts[f]+=1
  edge=max(counts,key=counts.get);edges.remove(edge);portals.append(list(edge))
 score=cost(best,edges)
 rnd=random.Random(w);ids=list(best)
 for step in range(3000):
  key=rnd.choice(ids);old=best[key];size=28*(1-step/4000)
  best[key]=[max(70,min(930,old[0]+rnd.uniform(-size,size))),max(60,min(630,old[1]+rnd.uniform(-size,size)))]
  updated=cost(best,edges)
  if updated<score and not crossings(best,edges):score=updated
  else:best[key]=old
 assert not crossings(best,edges)
 out[w]={'points':{k:[round(x,3) for x in v] for k,v in best.items()},'roads':edges,'portals':portals}
 print(w,'crossings',crossings(best,edges),'portals',len(portals),'score',round(score),flush=True)
open('web/map-layouts.js','w',encoding='utf8').write('/* Planar embeddings of the authoritative base roads; no runtime simulation. */\nwindow.MapLayouts = '+json.dumps(out,ensure_ascii=False,separators=(',',':'))+';\n')
