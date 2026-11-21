#!/usr/bin/env python3
"""Build experimental Sea Power units from original Y-up, +Z-bow metre OBJ files.

No stock models, textures, registries or ammunition definitions are redistributed.
Registry names are checked against the user's installed game by the installer.
"""
from __future__ import annotations
import argparse, configparser, hashlib, json, math, re
from collections import defaultdict
from pathlib import Path
from PIL import Image

VERSION = '0.2.0'
# SeaPower.Constants.METER_TO_UNITY, directly verified in the 0.8.7 reference assembly.
METRES_PER_UNIT = 1 / 0.0148809375
ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / 'payload/RAN-Aurora-Australis'

def vec(p):
    return ','.join(f'{v / METRES_PER_UNIT:.9f}' for v in p)

def section(name, rows):
    return '[' + name + ']\n' + '\n'.join(rows) + '\n'

def write_ini(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'\xef\xbb\xbf' + text.replace('\n', '\r\n').encode())

def read_obj(path):
    verts=[]; faces=[]; obj='Hull'; mat='hull'
    for line in path.read_text().splitlines():
        s=line.split()
        if not s: continue
        if s[0]=='v': verts.append(tuple(map(float,s[1:4])))
        elif s[0] in ('o','g'): obj=s[1]
        elif s[0]=='usemtl': mat=s[1]
        elif s[0]=='f':
            ids=[int(x.split('/')[0]) for x in s[1:]]
            ids=[i-1 if i>0 else len(verts)+i for i in ids]
            for i in range(1,len(ids)-1): faces.append((obj,mat,tuple(verts[j] for j in (ids[0],ids[i],ids[i+1]))))
    assert verts and faces, 'No source geometry'
    return faces

def read_colors(path):
    colors={}; name='hull'
    for line in path.read_text().splitlines():
        s=line.split()
        if not s: continue
        if s[0]=='newmtl': name=s[1]
        elif s[0]=='Kd': colors[name]=[float(x) for x in s[1:4]]
    return colors

def safe(s): return re.sub('[^A-Za-z0-9_]', '_', s)

def native_mesh(source, anchors, path):
    """Localize authored weapon meshes and split all materials per object."""
    # Authored hull faces previously wound inward. Rendering both sides concealed
    # that error, but the single-sided collision mesh needs outward winding.
    authored_hull=[tri for obj,mat,tri in source if obj.startswith('Hull_160m_continuous_icebreaking_form')]
    def signed_volume(tris):
        return sum(a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+a[2]*(b[0]*c[1]-b[1]*c[0]) for a,b,c in tris)/6
    original_hull_volume=signed_volume(authored_hull)
    reverse_hull=original_hull_volume<0
    source=[(obj,mat,tri[::-1] if reverse_hull and obj.startswith('Hull_160m_continuous_icebreaking_form') else tri) for obj,mat,tri in source]
    groups=defaultdict(list); mats={}; positions={}; parents={}
    roots=['GunYaw','GunBarrel','CIWSYaw1','CIWSBarrel1','CIWSYaw2','CIWSBarrel2']
    roots += [f'MGYaw{i}' for i in range(1,5)] + [f'MGBarrel{i}' for i in range(1,5)]
    propulsion_roots=[k for k in anchors if re.fullmatch(r'(Propeller|Rudder)[0-9]+',k)]
    roots += propulsion_roots
    # The visible screws/rudders must be the meshes named by the native mounts,
    # rather than leaving real hardware static while tiny marker triangles move.
    authored_moving={}
    moving_points=defaultdict(list)
    for obj,mat,tri in source:
        if obj.startswith(('Propeller_hub','Ice_strengthened_propeller_blade','Centre_propeller_hub','Centre_ice_propeller_blade')):
            moving_points[obj].extend(tri); authored_moving[obj]='Propeller'
        elif obj.startswith(('Ice_protected_rudder','Centre_rudder')):
            moving_points[obj].extend(tri); authored_moving[obj]='Rudder'
    for obj,prefix in list(authored_moving.items()):
        ps=moving_points[obj]; center=tuple(sum(p[k] for p in ps)/len(ps) for k in range(3))
        candidates=[n for n in propulsion_roots if n.startswith(prefix)]
        assert candidates, ('No native mount for authored moving part',obj)
        authored_moving[obj]=min(candidates,key=lambda n:sum((center[k]-anchors[n][k])**2 for k in range(3)))
    dynamic_parents={'GunBarrel':'GunYaw','CIWSBarrel1':'CIWSYaw1','CIWSBarrel2':'CIWSYaw2'}
    dynamic_parents.update({f'MGBarrel{i}':f'MGYaw{i}' for i in range(1,5)})
    root_material={}
    hull_faces=[]
    for obj,mat,tri in source:
        if obj.startswith('Hull_160m_continuous_icebreaking_form'): hull_faces.append(tri)
        root=authored_moving.get(obj) or next((r for r in sorted(roots,key=len,reverse=True) if obj==r or obj.startswith(r+'_') or obj.startswith(r+'.')),None)
        if root:
            assert root in anchors, ('Missing weapon anchor',root)
            if root not in root_material: root_material[root]=mat
            name=root if mat==root_material[root] else safe(root+'_'+mat)
            anchor=anchors[root]
            tri=tuple(tuple(p[k]-anchor[k] for k in range(3)) for p in tri)
            if name==root:
                if root in dynamic_parents:
                    parent=dynamic_parents[root]; parents[name]=parent
                    positions[name]=tuple(anchor[k]-anchors[parent][k] for k in range(3))
                else: positions[name]=anchor
            else: parents[name]=root; positions[name]=(0,0,0)
        else: name=safe(obj+'_'+mat)
        groups[name].append(tri); mats[name]=mat
    assert hull_faces, 'Source needs named hull geometry for collision'
    groups['coll_hull_main']=hull_faces; mats['coll_hull_main']=next(iter(mats.values()))
    # Rig roots are explicit even if an authored part is absent. Their tiny
    # geometry is not an extra visible weapon; unresolved anchors fail above.
    for name in roots:
        if name not in anchors: continue
        if name not in groups:
            e=.001
            groups[name]=[((0,0,0),(e,0,0),(0,e,0))]
            mats[name]=next(iter(mats.values()))
            if name in dynamic_parents:
                parent=dynamic_parents[name]; parents[name]=parent
                positions[name]=tuple(anchors[name][k]-anchors[parent][k] for k in range(3))
            else: positions[name]=anchors[name]
    lines=['# White Meridian class. Native units, Y-up, +Z bow.']
    vindex=0; count=0; degenerate=0
    for name,tris in sorted(groups.items(), key=lambda pair: pair[0]=='coll_hull_main'):
        lines.extend(['o '+name,'usemtl '+safe(mats[name]),'s off'])
        # Keep OBJ position, UV and normal indices in lockstep. Sharing repeated
        # corners avoids emitting many copies of the same Unity vertex.
        corners = {}
        # Smooth broad curved hulls and round gun barrels within a 45 degree
        # crease; preserve manufactured flat corners elsewhere.
        smooth=('hull' in name.lower() and 'deck' not in name.lower() and name!='coll_hull_main') or 'Barrel' in name
        incident=defaultdict(list)
        if smooth:
            for tri in tris:
                a,b,c=tri;u=[b[k]-a[k]for k in range(3)];v=[c[k]-a[k]for k in range(3)]
                cr=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]);ln=math.sqrt(sum(x*x for x in cr))
                if ln<1e-12:continue
                nn=tuple(x/ln for x in cr)
                for p in tri:incident[tuple(round(x,5)for x in p)].append((nn,cr))
        for tri in tris:
            u=[tri[1][k]-tri[0][k] for k in range(3)]; v=[tri[2][k]-tri[0][k] for k in range(3)]
            cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
            length=math.sqrt(sum(x*x for x in cross))
            if length<1e-12: degenerate+=1; continue
            normal=tuple(x/length for x in cross)
            drop=max(range(3), key=lambda k:abs(normal[k])); axes=[k for k in range(3) if k!=drop]
            # Explicit reverse triangles avoid relying on an unverified cull key.
            vnormals=[]
            for p in tri:
                total=[0.,0.,0.]
                for nn,cr in incident.get(tuple(round(x,5)for x in p),[]):
                    if sum(nn[k]*normal[k]for k in range(3))>=math.sqrt(.5):
                        total=[total[k]+cr[k]for k in range(3)]
                le=math.sqrt(sum(x*x for x in total))
                vnormals.append(tuple(x/le for x in total)if le>1e-12 else normal)
            variants=[(tri,vnormals)] if name=='coll_hull_main' else [(tri,vnormals),(tri[::-1],[tuple(-x for x in nn)for nn in vnormals[::-1]])]
            for points,ns in variants:
                # The corrected external OBJ importer reflects X and reverses
                # winding. Encode its inverse; INI pivots stay in native axes.
                points = [(-x,y,z) for x,y,z in reversed(points)]
                ns = [(-x,y,z) for x,y,z in reversed(ns)]
                face = []
                for p, nn in zip(points, ns):
                    position = ' '.join(f'{x/METRES_PER_UNIT:.9f}' for x in p)
                    if name == 'coll_hull_main':
                        # Physics needs shared position indices, without UV/normal seams.
                        index = corners.get(position)
                        if index is None:
                            vindex += 1
                            index = corners[position] = vindex
                            lines.append('v '+position)
                        face.append(str(index))
                        continue
                    uv = f'{p[axes[0]]/2:.9f} {p[axes[1]]/2:.9f}'
                    vertex_normal = ' '.join(f'{x:.9f}' for x in nn)
                    key = (position, uv, vertex_normal)
                    index = corners.get(key)
                    if index is None:
                        vindex += 1
                        index = corners[key] = vindex
                        lines.extend(('v '+position, 'vt '+uv, 'vn '+vertex_normal))
                    face.append(f'{index}/{index}/{index}')
                lines.append('f '+' '.join(face))
                count += 1
    path.write_text('\n'.join(lines)+'\n')
    root=next(n for n in groups if n.startswith('Hull_160m_continuous_icebreaking_form') and mats[n]=='hull')
    names=[n for n in groups if n not in (root,'coll_hull_main')]
    ordered=[]
    while names:
        ready=[n for n in names if n not in parents or parents[n] in ordered or parents[n]==root]
        assert ready, ('Cyclic model parenting', names)
        for n in ready: ordered.append(n); names.remove(n)
    collision_volume=signed_volume(hull_faces)
    assert collision_volume>0, ('Hull collision winding must be outward',collision_volume)
    assert all(n in groups and len(groups[n])>1 for n in propulsion_roots), 'Visible propulsion/rudder mesh missing'
    return root, ordered, mats, positions, parents, {'source_triangles':len(source),'exported_triangles':count,'skipped_degenerate_source_triangles':degenerate,'native_objects':len(groups),'source_hull_signed_volume_m3':original_hull_volume,'hull_winding_corrected':reverse_hull,'collision_hull_signed_volume_m3':collision_volume,'authored_moving_parts':authored_moving,'visible_propulsion_meshes':propulsion_roots}

def ship_ini(unit,year,model,anchors):
    root,names,mats,pos,parents,stats=model
    folder='ships/'+unit+'/'; obj='aurora.obj,CORRECT_OBJ_ORIENTATION'
    rows=[]
    def sec(n,r): rows.append(section(n,r))
    sec('General',['UnitType=Vessel','NumberOfDCTeams=4','DefaultCameraDistance=3.2','MinCameraDistanceForeAft=1.5','MinCameraDistanceBroadside=0.7','CameraPivotHeight=0.25','Length=160','Beam=29','CompartmentsHeight=0.13','ArmorType=Minor','FrontalArea=650','SideArea=3600','BottomArea=4000'])
    sec('OpticalView',['Views=binocular_7x50,binocular_10x50','DefaultView=binocular_7x50'])
    # SAR aircraft facilities are represented by authored hangar and pad only.
    # No ASW-capable stock aircraft is silently substituted for a rescue aircraft.
    sec('Physics',['Displacement=28000','MaxForwardVelocity=18','TelegraphVelocities=-5,0,3,6,10,15,18','MaxBackwardVelocity=5','LinearDrag=0.96','MaxAccelerationFactor=0.22','MinAccelerationFactor=0.06','RudderTurnRate=3','RudderForce=0.4','TiltFactor=1.1','PitchFactor=0','TrimDepth=0','TrimAngle=0','CenterToKeelDist=0','CenterOfMass='+vec((0,-1.5,0)),'CavitationSpeed=7'])
    sec('Buoyancy',['Density=0.5','OutOfWaterDrag=25','SubmergedDrag=25'])
    sec('SensorData',['VisualIdentificationRange=15','IRSignature=Large','RCS=Large','BaseNoise=160','FlowNoise=1','CavitationNoise=10','BladesCount=5','MinNoiseClassificationTreshold=5','ElectricFrequency=60'])
    sec('AI',['UnitCostValue=1000','UnitScoreValue=2','Role=ASuW','AAW_Capability=1','ASuW_Capability=1','ASW_Capability=0','HasChaff=False','MissilesToSaturate=2','TorpedoesToSaturate=1'])
    sec('ControlSystem',['Collider=coll_bridge','ArmorType=Minor','ModuleType=CIC'])
    sec('MainPowerSystem',['Type=Nuclear','HorsePower=60000','ArmorType=Minor','IsCoveredByMainArmor=True','Collider=coll_engine'])
    shafts=sum(k.startswith('Propeller')for k in anchors)
    sec('PropulsionSystems',[f'NumberOfPropulsionSystems={shafts}']); sec('RudderSystems',[f'NumberOfRudderSystems={shafts}'])
    for i in range(1,shafts+1):
        sec(f'PropulsionSystem{i}',[f'Mount=Propeller{i}','RotationDirection='+('Right' if i==1 else 'Left'),f'Collider=coll_prop_{i}'])
        sec(f'RudderSystem{i}',[f'Mount=Rudder{i}',f'Collider=coll_rudder_{i}'])
    optical_pivots={2000:(-6.2,23.55,19),2010:(0,23.55,33),2020:(8.7,23.5,31)}
    sensors=[('Visual','Optics',anchors.get('Optics',optical_pivots[year]),'coll_bridge'),('Radar','SPS-55',anchors.get('Radar',(0,32.9 if year==2000 else 33,20)),'coll_radar')]
    if year>=2010: sensors.append(('ESM','AN/SLQ-32_ESM',anchors.get('ESM',(0,29,20)),'coll_radar'))
    sec('SensorSystems',[f'NumberOfSensorSystems={len(sensors)}'])
    for i,(typ,name,p,coll) in enumerate(sensors,1): sec(f'SensorSystem{i}',[f'Type={typ}',f'SystemName={name}','Mount=Dummy','MountPosition='+vec(p),f'Collider={coll}'])
    weapons=[]
    def weapon(typ,name,r): weapons.append([f'Type={typ}',f'SystemName={name}']+r)
    # M242 is the verified 25mm stock Bushmaster gameplay proxy. The native
    # CIWS class uses projectile interception/burst semantics; no missile role.
    weapon('CIWS','M242',['Mount=GunYaw','IsMountRotatable=True','ContainerBase=GunBarrel','Gun=GunBarrel','AreContainersRotatable=True','Automatic=False','WorksStandalone=True','FiringArcs=-120,120','ElevationArc=-10,60','AssociatedMagazine=MagazineGun','Collider=coll_gun'])
    for i in (1,2):
        weapon('CIWS','MK15_Blk1',[f'Mount=CIWSYaw{i}','IsMountRotatable=True',f'ContainerBase=CIWSBarrel{i}',f'Gun=CIWSBarrel{i}','AreContainersRotatable=True','Automatic=True','WorksStandalone=True','FiringArcs='+('-180,0' if i==1 else '0,180'),'ElevationArc=-5,85','AssociatedMagazine=MagazineCIWS',f'Collider=coll_ciws_{i}'])
    for i in range(1,5):
        weapon('CIWS','50BMG',[f'Mount=MGYaw{i}','IsMountRotatable=True',f'ContainerBase=MGBarrel{i}',f'Gun=MGBarrel{i}','AreContainersRotatable=True','Automatic=False','WorksStandalone=True','FiringArcs='+('-175,-5' if anchors[f'MGYaw{i}'][0]<0 else '5,175'),'ElevationArc=-15,60','AssociatedMagazine=MagazineMG',f'Collider=coll_mg_{i}'])
    sec('WeaponSystems',[f'NumberOfWeaponSystems={len(weapons)}'])
    for i,w in enumerate(weapons,1): sec(f'WeaponSystem{i}',w)
    for name,ammo,count,coll in [('MagazineGun','usn_cal_25mm_m2',1200,'coll_gun_mag'),('MagazineCIWS','usn_cal_20mm_apds',3100,'coll_ciws_mag'),('MagazineMG','usn_cal_05in',8000,'coll_mg_mag')]:
        sec(name,['NumberOfAmmunitionTypes=1',f'Collider={coll}','ModuleType=SmallMagazine','ArmorType=Minor',f'Ammunition1={ammo}',f'Ammunition1_Count={count}'])
    sec('Compartments',['Compartment1FirePosition='+vec((0,2,50)),'Compartment2FirePosition='+vec((0,2,0)),'Compartment3FirePosition='+vec((0,2,-50))])
    sec('Models',['LODLevels=1','LOD1Distance=1.0',f'ResourcesFolder={folder}',f'ResourcesRoot={obj}',f'ResourcesMesh={root}',f'ResourcesMaterialFolder={folder}',f'ResourcesMaterial={safe(mats[root])}_mat.ini','ResourcesMeshHullCollider=coll_hull_main'])
    sec('Submodels',[f'Main_{i}={n}' for i,n in enumerate(names,1)])
    for n in names:
        r=[f'ResourcesMeshFolder={folder}',f'RootMesh={obj}',f'Mesh={n}',f'ResourcesMaterialFolder={folder}',f'Material={safe(mats[n])}_mat.ini']
        if n in parents:r.append('Parent='+parents[n])
        if n in pos:r.append('Position='+vec(pos[n]))
        sec(n,r)
    colls={'coll_bridge':((0,19,18),(24,12,25)),'coll_engine':((0,-1,-5),(20,14,40)),'coll_radar':((0,29,20),(6,12,10)),'coll_gun':(anchors['GunYaw'],(4,4,5)),'coll_gun_mag':((0,4,54),(6,5,6)),'coll_ciws_mag':((0,7,-12),(6,5,8)),'coll_mg_mag':((0,6,8),(5,3,5))}
    for i in (1,2):colls[f'coll_ciws_{i}']=(anchors[f'CIWSYaw{i}'],(4,5,4))
    for i in range(1,shafts+1):
        colls[f'coll_prop_{i}']=(anchors[f'Propeller{i}'],(5,5,3)); colls[f'coll_rudder_{i}']=(anchors[f'Rudder{i}'],(1,5,4))
    for i in range(1,5):colls[f'coll_mg_{i}']=(anchors[f'MGYaw{i}'],(1.5,2,1.5))
    sec('Colliders',['UseKinematicCollision=True','NumberOfMeshColliders=2','MeshCollider1=coll_hull_main','MeshCollider2=coll_hull_kinematic',f'NumberOfColliders={len(colls)}']+[f'Collider{i}={n}'for i,n in enumerate(colls,1)])
    sec('coll_hull_main',['Collider=coll_hull_main','Kinematic=False'])
    sec('coll_hull_kinematic',['Collider=coll_hull_main','Kinematic=True'])
    for n,(p,d) in colls.items():sec(n,['Collider=Box','Position='+vec(p),'Rotation=0,0,0','Scale='+vec(d)])
    sec('Foam',['HullFoamTexture=ships/particles/wake/Ceto_Hullwake','HullFoamPosition='+vec((0,0,35)),'HullFoamDuration=20','HullFoamSize=0.5','HullFoamSpacing=0.55','HullFoamExpansion=0.055','HullFoamAlpha=2','SternFoamTexture=ships/particles/wake/Ceto_Propwash','SternFoamPosition='+vec((0,0,-74)),'SternFoamDuration=30','SternFoamSize=0.5','SternFoamSpacing=0.45','SternFoamExpansion=0.025','SternFoamAlpha=2','VelocityForMaxParticles=15'])
    return '; Experimental fictional RAN icebreaker. No live-game validation.\n'+'\n'.join(rows)

def validate(path,obj):
    c=configparser.ConfigParser(interpolation=None,strict=True);c.optionxform=str;c.read(path,encoding='utf-8-sig')
    objects=set(re.findall(r'^o (.+)$',obj.read_text(),re.M)); names=set(c['Submodels'].values())|{c['Models']['ResourcesMesh'],'Dummy'}
    for n in c['Submodels'].values():assert c[n]['Mesh'] in objects
    for n in c:
        for k in ('Mount','Gun','ContainerBase','Parent'):
            if k in c[n]:assert c[n][k] in names,(n,k,c[n][k])
        for k in ('Collider','AssociatedMagazine'):
            if k in c[n]:
                for v in c[n][k].split(','):assert v in c or v=='Box',(n,k,v)
    assert len([n for n in c if re.fullmatch('WeaponSystem[0-9]+',n)])==7
    assert all(c[n].get('Type') not in ('Missile','Torpedo') for n in c)
    assert c['MainPowerSystem']['Type']=='Nuclear'
    assert not any('Sonar'==c[n].get('Type') for n in c)
    return {'unit':path.stem,'sections':len(c),'objects':len(objects),'cross_references':'passed','weapons':7,'missiles':0,'torpedoes':0,'nuclear_type':'verified stock enum','game_runtime_tested':False}

def make_manifest():
    files={p.relative_to(MOD).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(MOD.rglob('*')) if p.is_file()}
    (ROOT/'package-manifest.json').write_text(json.dumps({'schema':1,'mod_id':'ran_aurora_australis','version':VERSION,'files':files},indent=2)+'\n')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);args=ap.parse_args()
    anchor_path=args.source/'anchors.json'
    if anchor_path.exists():
        anchors_data=json.loads(anchor_path.read_text()); anchors=anchors_data.get('anchors',anchors_data)
    else:
        data=json.loads((args.source/'Aurora-Model-Manifest.json').read_text());anchors={}
        for mount in data['mounts']:
            anchors[mount['yaw_object']]=mount['native_base_m'];anchors[mount['barrel_object']]=mount['native_barrel_pivot_m']
        for prefix,key in [('Propeller','propeller_anchors_m'),('Rudder','rudder_anchors_m')]:
            for i,p in enumerate(data[key],1):anchors[prefix+str(i)]=p
    MOD.mkdir(parents=True,exist_ok=True); names=[]; checks=[]
    for year in (2000,2010,2020):
        source=args.source/f'aurora_{year}.obj';mtl=source.with_suffix('.mtl')
        if not source.exists():raise FileNotFoundError(source)
        colors=read_colors(mtl);unit=f'ran_agb_aurora_{year}';ship=MOD/'ships'/unit;ship.mkdir(parents=True,exist_ok=True)
        model=native_mesh(read_obj(source),anchors,ship/'aurora.obj')
        for mat in set(model[2].values()):
            col=tuple(max(0,min(255,round(x*255))) for x in colors.get(mat,[.55,.59,.6]))
            name=safe(mat);image=Image.new('RGBA',(128,128));pixels=[]
            seed=int.from_bytes(hashlib.sha256(name.encode()).digest()[:4],'little')
            for y in range(128):
                for x in range(128):
                    noise=(((x*1973)^(y*9277)^seed)&7)-3
                    pixels.append(tuple(max(0,min(255,c+noise//2))for c in col)+(255,))
            image.putdata(pixels);image.save(ship/(name+'.png'))
            shine=100 if 'glass'in name.lower() else 20 if 'deck'in name.lower() else 32
            Image.new('RGBA',(128,128),(shine,shine,shine,255)).save(ship/(name+'_spec.png'))
            write_ini(ship/(name+'_mat.ini'),section('Shader',['Path=Marmoset/Bumped Specular IBL'])+'\n'+section('Textures',[f'_MainTex=ships/{unit}/{name}.png',f'_SpecTex=ships/{unit}/{name}_spec.png',f'_BumpMap=ships/{unit}/normal.png']))
        Image.new('RGBA',(128,128),(128,128,255,255)).save(ship/'normal.png')
        path=MOD/'vessels'/(unit+'.ini');write_ini(path,ship_ini(unit,year,model,anchors))
        write_ini(path.with_name(unit+'_variants.ini'),section('General',['NumberOfVariants=1'])+'\n'+section('Default',['Nation=Australia',f'ServiceDate={year}|2055'])+'\n'+section('Variant1',['Nation=Australia',f'ServiceDate={year}|2055']))
        fit = {2000:'as commissioned', 2010:'patrol refit', 2020:'polar surveillance refit'}[year]
        names.append(section(unit, [
            'Type=AGB,Nuclear Patrol Icebreaker',
            f'Default=White Meridian class ({year}),White Meridian {year}',
            'Variant1=HMAS Rimehaven,Rimehaven',
            f'DefaultDescription=HMAS Rimehaven is a fictional Australian nuclear-electric Antarctic patrol icebreaker in her {year} configuration ({fit}). Her broad waterline shoulders and sloping forebody are shaped for icebreaking. Her hangar and working deck support the design roles of fisheries patrol and rescue. Physical sea-ice fracture is unverified in Sea Power. Mod version {VERSION}.'
        ]))
        checks.append(validate(path,ship/'aurora.obj')|model[-1])
    write_ini(MOD/'language_en/vessel_names.ini','\n'.join(names))
    write_ini(MOD/'_info.ini',section('Language_en',[
        f'Name=RAN / HMAS Rimehaven v{VERSION}',
        'Description=White Meridian-class fictional Antarctic patrol icebreaker. Includes the 2000, 2010 and 2020 configurations of HMAS Rimehaven.'
    ])+'\n'+section('Compatibility',['; Compatibility target carried forward from v0.1.0.','ApproximateVersion=0.9.0']))
    deps={'schema':1,'files':[{'path':p} for p in ['ammunition/usn_cal_25mm_m2.ini','ammunition/usn_cal_20mm_apds.ini','ammunition/usn_cal_05in.ini','systems/weapons.ini','systems/sensors.ini']],'weapon_systems':['M242','MK15_Blk1','50BMG'],'sensor_systems':['Optics','SPS-55','AN/SLQ-32_ESM'],'combat_systems':[]}
    (MOD/'DEPENDENCIES.json').write_text(json.dumps(deps,indent=2)+'\n')
    report={'version':VERSION,'ship':'HMAS Rimehaven','class':'White Meridian','status':'offline native cross-reference checks passed','game_runtime_tested':False,'units':checks,'metres_per_game_unit':METRES_PER_UNIT,'source_axes':'X starboard / Y up / Z bow','limitations':['No dynamic ice fracture, ice resistance or polar navigation simulation has been verified.','Nuclear is a verified native power-system enum; reactor engineering, refuelling and infinite mission endurance are not modeled or established.','2000/2010/2020 are separately selected units; no runtime module swapping or Refit Yard integration is claimed.','SPS-55 is a common stock surface-search radar proxy; 2010 and 2020 sensor improvements are mostly authored visual modules.','Native radar, ESM, gun operation, collider tuning and waterline require actual Sea Power testing.','SAR flight deck/hangar are modeled but an operational rescue helicopter is not registered, avoiding an ASW-armed aircraft substitute.','CIWS port/starboard firing arcs cover nominal 360-degree azimuth; elevation, close targets, ship motion, structures and flight operations still create practical limits.','Minor armor is a broad gameplay setting; the ice belt is not a heavy combat armor belt.']}
    (MOD/'NATIVE-INTEGRATION.json').write_text(json.dumps(report,indent=2)+'\n');(ROOT/'validation/NATIVE-CHECKS.json').write_text(json.dumps(report,indent=2)+'\n')
    make_manifest();print(json.dumps({'mod':str(MOD),'units':len(checks),'status':report['status']}))

if __name__=='__main__':main()
