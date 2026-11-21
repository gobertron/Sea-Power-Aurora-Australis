#!/usr/bin/env python3
"""Embed authored Rimehaven OBJ geometry in an offline WebGL model review."""
import argparse, base64, io, json, math, pathlib, struct, zlib
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent

def category(name):
    n = name.lower()
    if any(s in n for s in ('hull_160m','icebelt','ice_belt','rudder','shaft','skeg','propeller','ice_horn','icehorn','nozzle')): return 6
    if any(s in n for s in ('ciws','phalanx')): return 2
    if any(s in n for s in ('gun','cannon','browning','50cal','machine')): return 1
    if any(s in n for s in ('radar','eo_','antenna','dome','mast','sensor','satcom')): return 3
    if any(s in n for s in ('crane','mission','container','rhib','boat','davit','rescue')): return 4
    if any(s in n for s in ('hangar','flight','heli')): return 5
    return 0

def read_obj(path):
    materials = {}
    for mp in [path.with_suffix('.mtl')]:
        key = None
        for line in mp.read_text(errors='replace').splitlines():
            parts = line.split()
            if not parts: continue
            if parts[0] == 'newmtl': key = ' '.join(parts[1:])
            elif parts[0] == 'Kd' and key: materials[key] = list(map(float, parts[1:4]))
    v, vn, out = [], [], bytearray()
    mat, name = '', ''
    mesh_names = []
    bounds = [[float('inf')]*3,[float('-inf')]*3]
    def index(s, arr):
        x=int(s); return arr[x-1 if x>0 else x]
    for line in path.read_text(errors='replace').splitlines():
        p=line.split()
        if not p: continue
        if p[0]=='v':
            x=list(map(float,p[1:4])); v.append(x)
            for i in range(3): bounds[0][i]=min(bounds[0][i],x[i]);bounds[1][i]=max(bounds[1][i],x[i])
        elif p[0]=='vn': vn.append(list(map(float,p[1:4])))
        elif p[0]=='usemtl': mat=' '.join(p[1:])
        elif p[0] in ('o','g'):
            name=' '.join(p[1:]);mesh_names.append(name)
        elif p[0]=='f':
            f=[s.split('/') for s in p[1:]]
            for i in range(1,len(f)-1):
                tri=[f[0],f[i],f[i+1]]; pos=[index(a[0],v) for a in tri]
                a=[pos[1][j]-pos[0][j] for j in range(3)];b=[pos[2][j]-pos[0][j] for j in range(3)]
                normal=[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
                size=math.sqrt(sum(q*q for q in normal)) or 1;normal=[q/size for q in normal]
                col=materials.get(mat,[.51,.56,.60]);cat=category(name)
                for pnt,elem in zip(pos,tri):
                    n=index(elem[2],vn) if len(elem)>2 and elem[2] else normal
                    out.extend(struct.pack('<10f',*(pnt+n+col+[cat])))
    return {'data':base64.b64encode(zlib.compress(bytes(out),9)).decode(), 'vertices':len(out)//40,
            'triangles':len(out)//120, 'bounds':bounds, 'meshes':len(set(mesh_names)),
            'source':path.name, 'bytes':len(out)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', type=pathlib.Path, default=ROOT.parent / 'model')
    parser.add_argument('--output', type=pathlib.Path, default=ROOT.parents[1] / 'HMAS-Rimehaven-3D.html')
    parser.add_argument('--reference', type=pathlib.Path, default=ROOT.parents[1] / 'docs' / 'Rimehaven-Hull-Study.png')
    args = parser.parse_args()
    models = {}
    for year in (2000, 2010, 2020):
        source = args.models / f'aurora_{year}.obj'
        models[str(year)] = read_obj(source)
        print(year, source.name, models[str(year)]['triangles'], 'triangles')
    template = (ROOT / 'viewer-template.html').read_text()
    script = (ROOT / 'viewer.js').read_text()
    content = template.replace('__VIEWER_JS__', script).replace('__MODELS__', json.dumps(models, separators=(',', ':')))
    with Image.open(args.reference) as reference:
        reference.thumbnail((1120, 850))
        packed = io.BytesIO()
        reference.convert('RGB').save(packed, format='WEBP', quality=86)
    content = content.replace('__PLATE__', base64.b64encode(packed.getvalue()).decode('ascii'))
    args.output.write_text(content, encoding='utf-8')
    print(args.output, args.output.stat().st_size, 'bytes')


if __name__ == '__main__':
    main()
