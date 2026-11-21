"""Static artifact checks, not a Sea Power game test."""
from pathlib import Path
import json, math, hashlib
from collections import Counter,defaultdict
p=Path(__file__).parent
m=json.loads((p/'Aurora-Model-Manifest.json').read_text());results=[]
for yr in m['era_variants']:
 verts=[];faces=[];names=[];mtls=set();face_max=0;parts=defaultdict(list);hull=[]
 for l in (p/f'aurora_{yr}.obj').read_text().splitlines():
  a=l.split()
  if not a:continue
  if a[0]=='v':
   vertex=tuple(map(float,a[1:4]));verts.append(vertex);parts[names[-1]].append(vertex)
  elif a[0]=='o':names.append(a[1])
  elif a[0]=='f':
   faces.append([int(t.split('/')[0]) for t in a[1:]])
   face_max=max(face_max,max(faces[-1]))
   if names[-1].startswith('Hull_160m_'):hull.append(faces[-1])
  elif a[0]=='usemtl':mtls.add(a[1])
 checks={'finite_vertices':all(all(math.isfinite(x) for x in v) for v in verts),'valid_indices':face_max<=len(verts),'triangles_only':all(len(f)==3 for f in faces),'required_weapon_objects':all(n in names for n in ['GunYaw','GunBarrel','CIWSYaw1','CIWSYaw2','CIWSBarrel1','CIWSBarrel2','MGYaw1','MGBarrel1','MGYaw4','MGBarrel4']),'no_missile_torpedo_mesh':not any(any(s in n.lower() for s in ['missile','torpedo','vls']) for n in names),'no_detached_thruster_symbols':not any('thruster' in n.lower() for n in names)}
 def matching(prefix):
  return [points for name,points in parts.items() if name.startswith(prefix)]
 edges=Counter(tuple(sorted((a,b))) for f in hull for a,b in zip(f,f[1:]+f[:1]))
 checks['closed_collision_source']=bool(hull) and all(n==2 for n in edges.values())
 shell=matching('Hull_160m_')[0]
 draft=-min(y for x,y,z in shell)
 hull_beam=max(x for x,y,z in shell)-min(x for x,y,z in shell)
 length=max(z for x,y,z in shell)-min(z for x,y,z in shell)
 checks['moulded_dimensions']=all(abs(value-target)<.001 for value,target in [(length,160),(hull_beam,29),(draft,9.5)])
 # Intersect the actual shell facets with the design waterplane. Measurements
 # are evidence of the modelled shape and do not establish resistance in ice.
 intersections=[]
 for face in hull:
  pts=[verts[i-1] for i in face]
  for a,b in zip(pts,pts[1:]+pts[:1]):
   if (a[1]<0)!=(b[1]<0):
    fraction=-a[1]/(b[1]-a[1])
    intersections.append((a[0]+(b[0]-a[0])*fraction,a[2]+(b[2]-a[2])*fraction))
 deck_stem=max(z for x,y,z in shell)
 forefoot_underhang=deck_stem-max(z for x,z in intersections)
 checks['raked_stem_at_waterplane']=5<forefoot_underhang<9
 checks['fixed_ice_protection_present']=all(len(matching(prefix))==count for prefix,count in [
     ('Fixed_ice_nozzle',3),('Fixed_after_ice_horn',3),('Nozzle_V_bracket',6),('Forefoot_ice_skeg',1),
     ('Forecastle_weather_bulwark',2),('Ice_searchlight_housing',2)])
 # Project each moving blade on its own shaft's radial plane; compare its
 # maximum swept radius with the inscribed radius of the narrowest nozzle.
 clearance=[]
 for cx,cy,cz in m['propeller_anchors_m']:
  blades=[p for prefix in ('Centre_ice_propeller_blade','Ice_strengthened_propeller_blade')
          for p in matching(prefix) if abs(sum(v[0] for v in p)/len(p)-cx)<2]
  shroud=next(p for p in matching('Fixed_ice_nozzle') if abs(sum(v[0] for v in p)/len(p)-cx)<.001)
  swept=max(math.hypot(x-cx,y-cy) for p in blades for x,y,z in p)
  bore=min(math.hypot(x-cx,y-cy) for x,y,z in shroud)*math.cos(math.pi/40)
  clearance.append({'shaft_x_m':cx,'blades':len(blades),'swept_radius_m':round(swept,3),
                    'minimum_radial_clearance_m':round(bore-swept,3)})
 checks['screw_rotation_clears_nozzles']=all(r['blades']==5 and r['minimum_radial_clearance_m']>.04 for r in clearance)
 shape={'deck_stem_overhang_ahead_of_waterline_m':round(forefoot_underhang,3),
        'waterline_length_m':round(max(z for x,z in intersections)-min(z for x,z in intersections),3),
        'hull_length_m':length,'hull_beam_m':hull_beam,'draft_m':draft,
        'hull_triangles':len(hull),'undirected_hull_edges':len(edges),'screw_clearance':clearance}
 b={r['object']:r for r in m['bounds'] if r['era']==yr};contact=[]
 pairs=[('GunYaw','Gun30_base'),('CIWSYaw1','CIWS_foundation_1'),('CIWSYaw2','CIWS_foundation_2'),('CIWS_foundation_1','CIWS_sponson_1'),('CIWS_foundation_2','CIWS_sponson_2'),('CIWS_sponson_1','CIWS_support_1'),('CIWS_sponson_2','CIWS_support_2')]
 for top,base in pairs:
  a,c=b[top],b[base]
  horiz=all(min(a['max'][k],c['max'][k])-max(a['min'][k],c['min'][k])>=0 for k in [0,2])
  gap=a['min'][1]-c['max'][1]
  contact.append({'object':top,'support':base,'horizontal_overlap':horiz,'vertical_gap_m':round(gap,5),'pass':horiz and gap<=.03})
 checks['all_major_mounts_supported']=all(r['pass'] for r in contact)
 results.append({'era':yr,'vertices':len(verts),'triangles':len(faces),'objects':len(names),'materials':sorted(mtls),'checks':checks,'mount_contacts':contact,'polar_geometry':shape})
report={'status':'PASS' if all(all(r['checks'].values()) for r in results) else 'FAIL','scope':'Static mesh, native-axis and mount-contact checks only. Not in-game firing, icebreaking, stability, armour or propulsion validation.','results':results,'source_sha256':hashlib.sha256((p/'build_aurora.py').read_bytes()).hexdigest(),'review_views':['overview','port quarter','starboard profile','plan'],'needs_live_game_check':['CIWS masked arcs and target tracking','Gun training animation and muzzle origin','Waterline and hull placement','Helicopter landing']}
(p/'Aurora-Model-Validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'status':report['status'],'eras':[{k:r[k] for k in ['era','vertices','triangles','objects']} for r in results]},indent=2))

raise SystemExit(0 if report['status']=='PASS' else 1)
