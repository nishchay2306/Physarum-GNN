"""Build the bundled fictional map used by the interactive simulation."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'data' / 'custom_city.json'


def build():
    nodes, edges = {}, []
    def present(x, y):
        return not (3 <= x <= 5 and 2 <= y <= 3 or 12 <= x <= 13 and 7 <= y <= 8)
    for y in range(11):
        for x in range(16):
            if present(x, y): nodes[f'{x}:{y}'] = [105+55*x, 90+55*y]
    for y in range(11):
        for x in range(16):
            u = f'{x}:{y}'
            if u not in nodes: continue
            for dx,dy in ((1,0),(0,1)):
                nx,ny=x+dx,y+dy;v=f'{nx}:{ny}'
                if v not in nodes or (dx and x==8 and y not in (2,5,8)): continue
                bridge=bool(dx and x==8)
                avenue=(x in (2,7,10,14) if dy else y in (1,5,8))
                oneway=bool(not bridge and not avenue and ((dy and x in (4,12)) or (dx and y in (3,9))))
                a,b=(u,v) if not oneway or ((x+y)%2==0) else (v,u)
                edges.append({'id':1000+len(edges),'u':a,'v':b,'oneway':oneway,
                    'highway':'bridge' if bridge else ('primary' if avenue else 'residential'),
                    'bridge':bridge,'meters':125 if bridge else 108,'speed_kmh':35 if avenue or bridge else 25,
                    'geometry':[nodes[a],nodes[b]]})
    center=next(e['id'] for e in edges if {e['u'],e['v']}=={'8:5','9:5'})
    meta={'name':'Aster City','fictional':True,'width':1100,'height':760,
          'start':'2:5','target':'13:5','suggested_closure':center,
          'districts':[['NORTH QUAY',210,125],['OLD TOWN',200,385],['CIVIC CENTER',690,385],['GARDEN DISTRICT',720,575]],
          'landmarks':[['City Hospital',215,225,'hospital'],['Transit Hub',270,480,'station'],
             ['Museum of Aster',705,205,'museum'],['Fire Station',820,420,'fire'],
             ['Botanical Garden',365,225,'park'],['Riverside Market',690,470,'market'],
             ['North Reservoir',825,575,'water'],['University',155,590,'campus']],
          'parks':[[248,160,198,154],[740,495,190,145],[105,570,128,80]],
          'water':[[535,40,66,665],[775,545,105,75]]}
    OUT.write_text(json.dumps({'meta':meta,'nodes':nodes,'edges':edges},separators=(',',':')),encoding='utf8')
    print(f'Built fictional city: {len(nodes)} intersections, {len(edges)} roads; default bridge {center}')

if __name__=='__main__':build()
