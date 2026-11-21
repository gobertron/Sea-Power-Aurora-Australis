#!/usr/bin/env python3
"""Independent static geometry/rig checks; does not simulate the Sea Power loader.

Audit dependency: numpy/scipy. Production native builder only needs Pillow.
"""
from pathlib import Path
import argparse, collections, configparser, hashlib, importlib.util, json, math, re
import numpy as np
from scipy.spatial import cKDTree

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('aurora_builder',ROOT/'tools/build_native_aurora.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
MOD=ROOT/'payload/RAN-Aurora-Australis'

def load_obj(p):
    vertices=[];normals=[];texcoords=[];groups=collections.defaultdict(list);name='';indices_valid=True
    for l in p.read_text().splitlines():
        a=l.split()
        if not a:continue
        if a[0]=='v':vertices.append(tuple(map(float,a[1:4])))
        elif a[0]=='vn':normals.append(tuple(map(float,a[1:4])))
        elif a[0]=='vt':texcoords.append(tuple(map(float,a[1:3])))
        elif a[0]=='o':name=a[1]
        elif a[0]=='f':
            vi=[];ni=[]
            # Reproduce the corrected OBJ import reflection and reversed winding
            # before applying the independently stored native INI transforms.
            for x in reversed(a[1:]):
                fields=list(map(int,x.split('/')));v=fields[0]
                indices_valid &= 0<v<=len(vertices)
                px,py,pz=vertices[v-1];vi.append((-px,py,pz))
                if len(fields)==3:
                    t,n=fields[1:];indices_valid &= 0<t<=len(texcoords) and 0<n<=len(normals)
                    nx,ny,nz=normals[n-1];ni.append((-nx,ny,nz))
                else:assert len(fields)==1 and name=='coll_hull_main'
            if not ni:
                vv=np.asarray(vi);nn=np.cross(vv[1]-vv[0],vv[2]-vv[0]);nn=nn/np.linalg.norm(nn);ni=[nn]*3
            groups[name].append((vi,ni))
    return groups,indices_valid

def volume(tris):
    t=np.asarray(tris)
    return float(np.einsum('ij,ij->i',t[:,0],np.cross(t[:,1],t[:,2])).sum()/6)

results=[]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stock',type=Path,help='Optional reference original/ directory')
args=parser.parse_args()
def read_ini(path):
    c=configparser.ConfigParser(interpolation=None,strict=True);c.optionxform=str
    with path.open(encoding='utf-8-sig') as f:c.read_file(f)
    return c
names=read_ini(MOD/'language_en/vessel_names.ini')
assert set(names.sections())=={f'ran_agb_aurora_{y}' for y in (2000,2010,2020)}
for year in [2000,2010,2020]:
    unit=f'ran_agb_aurora_{year}'
    c=configparser.ConfigParser(interpolation=None,strict=True);c.optionxform=str
    c.read(MOD/f'vessels/{unit}.ini',encoding='utf-8-sig')
    groups,indices_valid=load_obj(MOD/f'ships/{unit}/aurora.obj')
    rendered=set(c['Submodels'].values())|{c['Models']['ResourcesMesh']}
    translations={}
    def world_position(name):
        if name in translations:return translations[name]
        if name not in c:return np.zeros(3)
        p=np.array([float(x) for x in c[name].get('Position','0,0,0').split(',')])*b.METRES_PER_UNIT
        if c[name].get('Parent'):p+=world_position(c[name]['Parent'])
        translations[name]=p;return p
    world_points=[];normal_dots=[];finite=True;nonzero=True
    for n,triangles in groups.items():
        ts=np.asarray([x[0] for x in triangles]);ns=np.asarray([x[1] for x in triangles])
        finite &= bool(np.isfinite(ts).all() and np.isfinite(ns).all())
        cross=np.cross(ts[:,1]-ts[:,0],ts[:,2]-ts[:,0]);lens=np.linalg.norm(cross,axis=1)
        nonzero &= bool((lens>1e-18).all())
        dots=np.einsum('ij,ikj->ik',cross/np.maximum(lens[:,None],1e-40),ns)
        normal_dots.extend(dots.ravel())
        if n in rendered:world_points.extend((ts*b.METRES_PER_UNIT+world_position(n)).reshape(-1,3))
    source_path=ROOT/f'source/model/aurora_{year}.obj'
    authored=b.read_obj(source_path)
    source_points=np.array([p for n,mat,t in authored for p in t])
    native_points=np.array(world_points)
    # Both directions catch omitted source components and spurious native parts.
    source_to_native=float(cKDTree(native_points).query(source_points)[0].max())
    native_to_source=float(cKDTree(source_points).query(native_points)[0].max())
    hull=np.array([t for n,mat,t in authored if n.startswith('Hull_')])
    collision=np.array([x[0] for x in groups['coll_hull_main']])*b.METRES_PER_UNIT
    edges=collections.Counter()
    for tri in collision:
        keys=[tuple(round(float(x),5) for x in p) for p in tri]
        for a,z in zip(keys,keys[1:]+keys[:1]):
            if a!=z:edges[tuple(sorted((a,z)))]+=1
    anchored={n:len(groups[n]) for n in groups if re.fullmatch(r'(Propeller|Rudder)[0-9]+',n)}
    models=c['Models']; folder=MOD/models['ResourcesFolder']
    obj,flag=models['ResourcesRoot'].split(',')
    assert flag=='CORRECT_OBJ_ORIENTATION' and (folder/obj).is_file()
    assert (MOD/models['ResourcesMaterialFolder']).resolve()==folder.resolve()
    material_files={folder/models['ResourcesMaterial']}
    for n in c['Submodels'].values():
        assert (MOD/c[n]['ResourcesMeshFolder']).resolve()==(MOD/c[n]['ResourcesMaterialFolder']).resolve()==folder.resolve()
        assert c[n]['Mesh']==n and c[n]['RootMesh']==models['ResourcesRoot']
        material_files.add(folder/c[n]['Material'])
    for p in material_files:
        assert all((MOD/rel).is_file() for rel in read_ini(p)['Textures'].values())
    assert set(groups)==rendered|{'coll_hull_main'}
    fit=read_ini(MOD/f'vessels/{unit}_variants.ini')
    assert fit['Default']['Nation']==fit['Variant1']['Nation']=='Australia'
    assert names[unit]['Variant1']=='HMAS Rimehaven,Rimehaven' and 'White Meridian' in names[unit]['Default']
    assert str(year) in names[unit]['Default'] and b.VERSION in names[unit]['DefaultDescription']
    wl=[]
    for tri in collision:
        for a,z in zip(tri,np.roll(tri,-1,axis=0)):
            if abs(a[1])<1e-7:wl.append(a)
            if a[1]*z[1]<0:wl.append(a+(z-a)*(-a[1]/(z[1]-a[1])))
    wl=np.asarray(wl);hp=collision.reshape(-1,3)
    fwd_below_7=float(hp[hp[:,1]<-7,2].max());fwd_wl=float(wl[:,2].max())
    width=float(np.ptp(hp[:,0]));length=float(np.ptp(hp[:,2]));draft=-float(hp[:,1].min())
    checks={
      'all_indices_valid':indices_valid,'all_positions_normals_finite':finite,
      'all_native_triangles_nonzero':nonzero,'normals_face_their_triangles':bool(min(normal_dots)>.69),
      'collision_not_a_rendered_submodel':'coll_hull_main' not in rendered,
      'collision_reference_resolves':c['Models']['ResourcesMeshHullCollider']=='coll_hull_main',
      'closed_collision_mesh':bool(edges) and all(n==2 for n in edges.values()),
      'outward_collision_winding':volume(collision)>0,
      'native_world_geometry_matches_source':max(source_to_native,native_to_source)<1e-5,
      'three_visible_screws_three_visible_rudders':len(anchored)==6 and min(anchored.values())>20,
      'all_mounts_and_parents_resolve':all(c[n][k] in rendered|{'Dummy'} for n in c for k in ['Mount','Parent','Gun','ContainerBase'] if k in c[n]),
      'dimensions_match_config':abs(width-float(c['General']['Beam']))<.002 and abs(length-float(c['General']['Length']))<.002 and abs(draft-9.5)<.002 and float(c['Physics']['CenterToKeelDist'])==float(c['Physics']['TrimDepth'])==0,
      'mesh_collider_section_resolves':c[c['Colliders']['MeshCollider1']]['Collider']==c[c['Colliders']['MeshCollider2']]['Collider']==c['Models']['ResourcesMeshHullCollider'] and [c[c['Colliders'][f'MeshCollider{i}']]['Kinematic'] for i in (1,2)]==['False','True'],
      'design_waterplane_intersects_hull':bool(np.ptp(wl[:,0])>22 and np.ptp(wl[:,2])>110),
      'rising_forefoot_beneath_waterline':fwd_below_7<fwd_wl-3 and fwd_wl<float(hp[:,2].max())-.5,
      'class_and_ship_renamed_and_registered':True,'all_materials_and_textures_found':True,
    }
    results.append({'unit_id':unit,'checks':checks,'materials_checked':len(material_files),'waterline_length_m':float(np.ptp(wl[:,2])),'waterline_beam_m':float(np.ptp(wl[:,0])),'waterline_foremost_station_m':fwd_wl,'foremost_station_below_7m_depth_m':fwd_below_7,'hull_length_beam_draft_m':[length,width,draft],'native_min_m':native_points.min(axis=0).tolist(),'native_max_m':native_points.max(axis=0).tolist(),'native_to_source_max_error_m':native_to_source,'source_to_native_max_error_m':source_to_native,'collision_signed_volume_m3':volume(collision),'collision_edge_multiplicities':dict(collections.Counter(edges.values())),'lowest_normal_face_dot':float(min(normal_dots)),'visible_moving_mesh_triangles':anchored})
report={'version':b.VERSION,'status':'PASS' if all(all(r['checks'].values()) for r in results) else 'FAIL','scope':'Offline native geometry and configuration audit; no Windows or Sea Power runtime test.','source_axis_convention':'X starboard, Y up, Z forward, authored design waterline Y=0 m','metres_per_native_unit':b.METRES_PER_UNIT,'units':results,'reference_assembly':{'file':'Seapower-Scripts.dll','reference_game_version':'0.8.7','reference_build_label':'261021 Public Release','source':'Sea Power project reference assembly, metadata inspection only. Stock data snapshot version independently unverified.','corrected_obj_import':'X reflected and face index order reversed; native positions independently encoded.','sha256':'eab2297ba92c6013958bdb2cf16d5794a4731330818ce353f89dc2241e16a3bd','SeaPower.Constants.METER_TO_UNITY':0.0148809375,'engine_loaded_in_game':False},'outstanding_game_checks':['Unit name and scenario loading','Actual game waterline and CORRECT_OBJ_ORIENTATION handling','Gun/radar/ESM operation','Propeller spin and rudder turning in game','Hull collision behaviour','Rescue flight operations (not registered)']}
if args.stock:
    stock=args.stock; reference='civ_ms_ivan_franko'
    p=stock/'vessels'/f'{reference}.ini'
    def stock_ini(source):
        ini=configparser.ConfigParser(interpolation=None,strict=False,allow_no_value=True,comment_prefixes=('#',';','//'),inline_comment_prefixes=('#',';','//'))
        ini.optionxform=str
        with source.open(encoding='utf-8-sig') as f:ini.read_file(f)
        return ini
    cfg=stock_ini(p)
    assert cfg['General']['UnitType']=='Vessel'
    assert {'ResourcesFolder','ResourcesRoot','ResourcesMesh','ResourcesMaterial'}<=set(cfg['Models'])
    assert len(cfg['Submodels'])>0 and 'Collider' in cfg[cfg['Colliders']['MeshCollider1']]
    assert 'Mount' in cfg['PropulsionSystem1'] and 'Mount' in cfg['RudderSystem1']
    assert {'Density','OutOfWaterDrag','SubmergedDrag'}<=set(cfg['Buoyancy'])
    localised=stock_ini(stock/'language_en/vessel_names.ini')
    assert {'Type','Default','Variant1','DefaultDescription'}<=set(localised[reference])
    assert {'Default','Variant1'}<=set(stock_ini(stock/'vessels'/f'{reference}_variants.ini'))
    deps=json.loads((MOD/'DEPENDENCIES.json').read_text())
    assert all((stock/item['path']).is_file() for item in deps['files'])
    for registry,key in [('sensors','sensor_systems'),('weapons','weapon_systems')]:
        source=(stock/'systems'/f'{registry}.ini').read_text(encoding='utf-8-sig')
        assert set(deps[key])<=set(re.findall(r'^\[([^\]]+)\]',source,re.M))
    report['stock_comparison']={'reference_id':reference,'description':'Ivan Franko class ice-strengthened passenger ship. Closest polar-service hull found in the stock vessel snapshot. Reference uses bundled meshes. Rimehaven uses external OBJ files.','vessel_ini_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'vanilla_snapshot_url':'https://github.com/SEST-HOBBY/Seapower-mods/blob/a0721c18f08b6e7fe3021e740854d326939d189c/mods-source/_vanilla/original/vessels/civ_ms_ivan_franko.ini','passed':['Models, submodels and collider section layout','Propeller and rudder mounts','Buoyancy and drag fields','Class and individual variant name registration','Declared stock ammunition files and sensor/weapon registry identifiers'],'scope':'Static comparison. Game build of the reference snapshot unverified.'}
(ROOT/f'validation/NATIVE-GEOMETRY-v{b.VERSION}.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':report['status'],'units':[{'unit':r['unit_id'],'checks':r['checks'],'max_error_m':max(r['native_to_source_max_error_m'],r['source_to_native_max_error_m'])} for r in results]},indent=2))
raise SystemExit(0 if report['status']=='PASS' else 1)
