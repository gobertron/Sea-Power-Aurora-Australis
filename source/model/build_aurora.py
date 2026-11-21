"""White Meridian class fictional nuclear Antarctic patrol icebreaker, mesh source.
Internal Blender axes: X starboard, Y bow, Z up. OBJ: X starboard, Y up, Z bow.
Public-facing design targets, not a validated naval architecture or ice-class rating.
Run: blender -b --python build_aurora.py -- /absolute/output/directory
"""
import bpy, math, json, sys, os
from pathlib import Path
from mathutils import Vector
OUT=Path(sys.argv[sys.argv.index('--')+1]) if '--' in sys.argv else Path(__file__).parent
OUT.mkdir(parents=True,exist_ok=True)
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
MAT={}
def mat(n,c,metal=0,rough=.55):
 m=bpy.data.materials.new(n); m.diffuse_color=(*c,1); m.use_nodes=True
 p=m.node_tree.nodes.get('Principled BSDF'); p.inputs['Base Color'].default_value=(*c,1);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough
 MAT[n]=m;return m
for n,c in {'hull':(.49,.54,.56),'lightgrey':(.65,.69,.69),'darkgrey':(.22,.27,.29),'underwater':(.29,.065,.055),'icebelt':(.09,.13,.15),'deck':(.17,.23,.25),'heli':(.12,.2,.21),'glass':(.018,.07,.09),'white':(.9,.93,.91),'black':(.025,.035,.035),'safety':(.96,.3,.045),'yellow':(.95,.71,.13),'nav_red':(.85,.025,.02),'nav_green':(.025,.65,.2),'blue':(.06,.23,.49),'module':(.56,.61,.59),'brass':(.48,.38,.15)}.items():mat(n,c,0.05 if n not in ['glass','white'] else 0,.25 if n=='glass' else .58)
ROOT=bpy.data.collections.new('WHITE_MERIDIAN_COMMON_HULL');bpy.context.scene.collection.children.link(ROOT)
ERAS={yr:bpy.data.collections.new('MODULE_'+str(yr)) for yr in [2000,2010,2020]}
for co in ERAS.values():bpy.context.scene.collection.children.link(co)
CUR=ROOT
def put(o,n,m):
 o.name=n
 for c in list(o.users_collection):c.objects.unlink(o)
 CUR.objects.link(o)
 o.data.materials.clear();o.data.materials.append(MAT[m]);return o
def cube(n,loc,dims,m='hull',bev=.06):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=put(bpy.context.object,n,m);o.dimensions=dims;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 if bev:
  md=o.modifiers.new('Edge radius','BEVEL');md.width=bev;md.segments=2
  bpy.context.view_layer.objects.active=o;bpy.ops.object.modifier_apply(modifier=md.name)
 return o
def cyl(n,loc,r,depth,m='hull',verts=16,rot=None):
 bpy.ops.mesh.primitive_cylinder_add(vertices=verts,radius=r,depth=depth,location=loc);o=put(bpy.context.object,n,m)
 if rot:o.rotation_euler=rot
 return o
def sphere(n,loc,r,m='white',scale=None):
 bpy.ops.mesh.primitive_uv_sphere_add(segments=20,ring_count=12,radius=r,location=loc);o=put(bpy.context.object,n,m)
 if scale:o.scale=scale
 for p in o.data.polygons:p.use_smooth=True
 return o
def beam(n,a,b,r=.07,m='lightgrey',verts=8):
 a=Vector(a);b=Vector(b);d=b-a;o=cyl(n,(a+b)*.5,r,d.length,m,verts);o.rotation_euler=d.to_track_quat('Z','Y').to_euler();return o
def mesh(n,v,f,m='hull'):
 me=bpy.data.meshes.new(n);me.from_pydata(v,[],f);me.update();o=bpy.data.objects.new(n,me);CUR.objects.link(o);o.data.materials.append(MAT[m]);return o
def text(n,s,loc,size=1,m='white',rot=(0,0,0),align='CENTER'):
 cu=bpy.data.curves.new(n,'FONT');cu.body=s;cu.align_x=align;cu.size=size;cu.extrude=.003;cu.space_character=1.1;o=bpy.data.objects.new(n,cu);CUR.objects.link(o);o.location=loc;o.rotation_euler=rot;cu.materials.append(MAT[m]);return o
def taper(n,y0,y1,z0,z1,wx0,wx1,m='hull'):
 v=[(-wx0,y0,z0),(wx0,y0,z0),(wx0,y1,z0),(-wx0,y1,z0),(-wx1,y0+.5,z1),(wx1,y0+.5,z1),(wx1,y1-.5,z1),(-wx1,y1-.5,z1)]
 return mesh(n,v,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],m)
def rail(n,pts,h=1.05):
 for j in range(len(pts)-1):
  a,b=Vector(pts[j]),Vector(pts[j+1]);d=(b-a).length
  for k in range(max(1,int(d/2.8))):
   p=a+(b-a)*(k/max(1,int(d/2.8)));beam(n+'_stanchion',p,p+Vector((0,0,h)),.037,'lightgrey',6)
  beam(n+'_top',a+Vector((0,0,h)),b+Vector((0,0,h)),.035,'lightgrey',6)
  beam(n+'_middle',a+Vector((0,0,h*.5)),b+Vector((0,0,h*.5)),.025,'lightgrey',6)
def ring(n,center,r,m='white',z=0,width=.12):
 x,y,zz=center;N=64;v=[]
 for rr in [r-width/2,r+width/2]:v += [(x+rr*math.cos(i*math.tau/N),y+rr*math.sin(i*math.tau/N),zz+z) for i in range(N)]
 return mesh(n,v,[(i,(i+1)%N,(i+1)%N+N,i+N) for i in range(N)],m)

# Station positions, deck half-breadths, keel and sheer heights, in metres.
stations = [
 (-80,3.8,.45,7.8),(-79,6.55,-.6,7.8),(-77,8.95,-1.85,7.8),
 (-74,10.95,-3.05,7.8),(-70,12.65,-4.7,7.8),(-65,13.65,-6.65,7.8),
 (-59,14.08,-8.05,7.8),(-51,14.31,-8.95,7.8),(-41,14.5,-9.4,7.8),
 (-31,14.5,-9.5,7.8),(-18,14.5,-9.5,7.8),(0,14.5,-9.5,7.8),
 (15,14.5,-9.48,7.8),(27,14.5,-9.3,7.8),(37,14.44,-8.98,7.8),
 (46,14.25,-8.41,7.8),(53,13.87,-7.56,7.8),(59,13.13,-6.34,7.8),
 (64,12.06,-4.85,7.8),(68,10.78,-3.22,7.88),(71,9.4,-1.62,8.04),
 (73.5,7.92,-.10,8.25),(75.5,6.46,1.33,8.45),(77,5.00,2.68,8.6),
 (78.4,3.4,4.36,8.72),(79.35,1.96,6.02,8.78),(79.82,.81,7.71,8.81),
 (80,.09,8.65,8.82)]
heights=(0,.045,.105,.19,.31,.46,.63,.81,1)
midship=(0,.44,.65,.80,.927,.98,.997,1,1)
spoon=(0,.215,.34,.47,.605,.74,.85,.94,1)
counter=(0,.29,.46,.61,.74,.86,.935,.98,1)

def section_offsets(station):
 y,w,bottom,deck=station
 bow_factor=min(1,max(0,(y-28)/41))
 stern_factor=min(1,max(0,(-y-47)/29))
 return [(w*(m+(s-m)*bow_factor+(a-m)*stern_factor),bottom+(deck-bottom)*t)
         for t,m,s,a in zip(heights,midship,spoon,counter)]

def section_at(y):
 for a,b in zip(stations,stations[1:]):
  if a[0]<=y<=b[0]:
   f=(y-a[0])/(b[0]-a[0])
   return [(x+(u-x)*f,z+(v-z)*f) for (x,z),(u,v) in zip(section_offsets(a),section_offsets(b))]
 raise ValueError('Station outside the hull: '+str(y))

def hull_breadth(y,z):
 sec=section_at(y)
 for (x,h),(u,k) in zip(sec,sec[1:]):
  if h<=z<=k:return x+(u-x)*(z-h)/(k-h)
 return sec[-1][0] if z>=sec[-1][1] else 0

def deck_at(y):return section_at(y)[-1][1]

verts=[]
for station in stations:
 starboard=section_offsets(station)
 perimeter=starboard+[(-x,z) for x,z in reversed(starboard[1:])]
 verts.extend((x,station[0],z) for x,z in perimeter)
N=len(perimeter);faces=[]
for j in range(len(stations)-1):
 for k in range(N):
  n=(k+1)%N
  faces.append((j*N+k,(j+1)*N+k,(j+1)*N+n,j*N+n))
faces += [tuple(range(N)),tuple((len(stations)-1)*N+i for i in reversed(range(N)))]

# Split each original face exactly at the fixed icebelt paint heights. This
# preserves the original geometric surface while avoiding stair-step material bands.
def clip_z(poly,cut,above):
 result=[]
 if not poly:return result
 for pa,pb in zip(poly,poly[1:]+poly[:1]):
  ina=pa[2]>=cut-1e-8 if above else pa[2]<=cut+1e-8
  inb=pb[2]>=cut-1e-8 if above else pb[2]<=cut+1e-8
  if ina:result.append(pa)
  if ina!=inb:
   t=(cut-pa[2])/(pb[2]-pa[2]);result.append(tuple(pa[k]+t*(pb[k]-pa[k]) for k in range(3)))
 return result
clipped_vertices=[];clipped_faces=[];paint_indices=[];vertex_map={}
for face in faces:
 for ti in range(1,len(face)-1):
  tri=[verts[face[k]] for k in [0,ti,ti+1]]
  for low,high,color in [(-100,-1.3,1),(-1.3,1.4,2),(1.4,100,3)]:
   poly=clip_z(clip_z(tri,low,True),high,False)
   if len(poly)<3:continue
   indices=[]
   for pp in poly:
    key=tuple(round(c,7) for c in pp)
    if key not in vertex_map:vertex_map[key]=len(clipped_vertices);clipped_vertices.append(pp)
    if not indices or vertex_map[key]!=indices[-1]:indices.append(vertex_map[key])
   if len(indices)>2 and indices[-1]==indices[0]:indices.pop()
   if len(set(indices))<3:continue
   clipped_faces.append(tuple(indices));paint_indices.append(color)
h=mesh('Hull_160m_continuous_icebreaking_form',clipped_vertices,clipped_faces)
for m in ['underwater','icebelt','hull']:h.data.materials.append(MAT[m])
for p,color in zip(h.data.polygons,paint_indices):
 p.material_index=color
 if max(h.data.vertices[i].co.z for i in p.vertices)-min(h.data.vertices[i].co.z for i in p.vertices)>.2:p.use_smooth=True
# The painted deck follows the sheer at each station.
deck_vertices=[(side*(w-.025),y,z+.012) for y,w,k,z in stations for side in [-1,1]]
deck_faces=[(2*i,2*i+1,2*i+3,2*i+2) for i in range(len(stations)-1)]
mesh('WeatherDeck_continuous',deck_vertices,deck_faces,'deck')

# Enclosed high-freeboard accommodation, forward bridge and sheltered side galleries.
taper('Accommodation_mainblock',-6,37,7.8,13.8,10.8,9.9)
taper('Forward_bridge_lower',15,37,13.8,18.8,9.8,9.15,'lightgrey')
taper('Bridge_panorama',13,36,18.8,22.2,11.1,10.7,'lightgrey')
cube('Bridge_roof',(0,24.5,22.45),(22.9,24.4,.5),'lightgrey',.15)
cube('Bridge_weather_brow',(0,35.7,21.6),(22.5,1.5,.28),'darkgrey')
# Continuous forward bridge glazing and side windows.
for i,x in enumerate([-9,-6.8,-4.5,-2.25,0,2.25,4.5,6.8,9]):
 o=cube('Bridge_front_glass_'+str(i),(x,35.81,20.6),(1.85,.08,1.25),'glass',.02);o.rotation_euler.x=math.atan(.5/3.4)
for side in [-1,1]:
 for j,y in enumerate([16,19,22,25,28,31,33.5]):o=cube('Bridge_side_glass',(side*10.95,y,20.6),(.07,2,1.25),'glass',.02);o.rotation_euler.y=-side*math.atan(.4/3.4)
 for y in range(-2,35,4):
  for z in [10.0,12.1]:cube('Cabin_porthole',(side*10.55,y,z),(.08,.95,.62),'glass',.06)
 cube('Enclosed_sheltered_gallery',(side*11.25,9.5,11.9),(1.4,31,2.35),'lightgrey')
 for y in range(-2,24,4):cube('Gallery_window',(side*11.97,y,12.2),(.06,1.9,.9),'glass',.03)
 # watertight access doors and escape stations.
 cube('Watertight_door',(side*10.84,32,8.9),(.12,1.1,2),'lightgrey')
 cube('Door_handle',(side*10.95,32.25,8.9),(.12,.18,.1),'black')
 cyl('Lifering',(side*11.0,29.3,10),.38,.1,'safety',20,(0,math.pi/2,0))
 rail('Bridge_roof_rail',[(side*11.1,13,22.71),(side*11.1,36,22.71)])

# One integrated aft hangar and large ice-capable helicopter deck.
taper('Single_helicopter_hangar',-40,-7,7.8,15.4,10.9,9.8)
cube('Hangar_roof',(0,-23.5,15.53),(20.4,33.2,.26),'deck')
cube('Hangar_roller_door',(0,-40.05,11.2),(11.4,.12,6.25),'darkgrey')
for z in [8.5,9,9.5,10,10.5,11,11.5,12,12.5,13,13.5,14]:cube('Hangar_roller_slat',(0,-40.14,z),(11.4,.035,.04),'lightgrey',0)
cube('Hangar_door_caution_top',(0,-40.16,14.4),(11.7,.08,.2),'yellow',0)
# Follow the narrowing afterbody to keep both aft deck corners connected.
aft_stations=[(-74.4,10.46),(-72,11.57),(-69,12.11),(-63,12.23),(-41.5,12.23)]
pad_vertices=[(side*w,y,z) for z in [7.80,7.90] for y,w in aft_stations for side in [-1,1]]
deck_n=2*len(aft_stations)
pad_faces=[(2*i,2*i+1,2*i+3,2*i+2) for i in range(len(aft_stations)-1)]
rim=[2*i for i in range(len(aft_stations))]+list(reversed([2*i+1 for i in range(len(aft_stations))]))
pad_faces=[tuple(j+deck_n for j in f) for f in pad_faces]+[tuple(reversed(f)) for f in pad_faces]+[(j,k,k+deck_n,j+deck_n) for j,k in zip(rim,rim[1:]+rim[:1])]
mesh('Helicopter_deck',pad_vertices,pad_faces,'heli')

ring('Helipad_circle',(0,-58,7.97),9.3,width=.2)
cube('Helipad_H_left',(-1.7,-58,8.0),(.37,5.5,.04),'white',0)
cube('Helipad_H_right',(1.7,-58,8.0),(.37,5.5,.04),'white',0)
cube('Helipad_H_cross',(0,-58,8.0),(3.6,.37,.04),'white',0)
cube('Helipad_landing_line',(0,-47.0,8.0),(.18,8,.04),'white',0)
for side in [-1,1]:
 for y in [-72,-66,-60,-54,-48]:cyl('Recessed_deck_lamp',(side*min(11.8,hull_breadth(y,7.8)-.55),y,7.93),.1,.04,'nav_green',8)
 # fold-down safety nets sit outboard, below flying surface.
 for y in [-72,-67,-62,-57,-52,-47]:
  net_x=min(12.18,hull_breadth(y,7.5)-.54)
  cube('Flightdeck_safety_net_frame',(side*(net_x+.48),y,7.72),(1.25,4.7,.09),'lightgrey',0)
  for j in range(5):beam('Safety_net_rope',(side*(net_x-.10),y-2.2+j,7.77),(side*(net_x+1.05),y-2.2+j,7.77),.018,'darkgrey',4)
 for y in [-73,-46]:cube('Flightdeck_fire_station',(side*min(11.4,hull_breadth(y,7.8)-.75),y,8.65),(.6,.8,1.5),'safety')
rail('Stern_rail',[(-7,-78,7.82),(-3.6,-79.77,7.82),(3.6,-79.77,7.82),(7,-78,7.82)])

# A shallow V breakwater drains shipped water outboard ahead of the wheelhouse.
for side in [-1,1]:
 line=[(0,46.6), (side*5.8,45.25), (side*9.1,43.8)]
 v=[(x,y+dy,7.8+dz) for x,y in line for dy,dz in [(-.25,0),(.32,0),(.04,1.12),(-.09,1.12)]]
 f=[(4*j+i,4*j+(i+1)%4,4*(j+1)+(i+1)%4,4*(j+1)+i) for j in range(2) for i in range(4)]
 mesh('Forward_sea_breakwater',v,f+[(3,2,1,0),(8,9,10,11)],'lightgrey')
# Aft rescue/service deck details, vents and low-speed manoeuvring gear.
for side in [-1,1]:
 for y in [-76,42,66]:
  x=side*(7.8 if y<0 else 9.1 if y<60 else 7.5)
  cube('Mooring_bollard_base',(x,y,7.95),(1.35,1,.25),'darkgrey')
  for dx in [-.38,.38]:cyl('Mooring_bollard',(x+dx,y,8.25),.15,.5,'darkgrey',10)
# Three ice nozzles and V-struts shelter the existing propulsion axes.
def screw_guard(x,z):
 n=40
 profile=[(-74.48,2.20),(-74.50,2.30),(-74.32,2.35),(-73.50,2.33),(-72.65,2.43),(-72.53,2.35),(-72.60,2.23),(-73.55,2.18)]
 v=[(x+r*math.cos(i*math.tau/n),y,z+r*math.sin(i*math.tau/n)) for y,r in profile for i in range(n)]
 f=[(j*n+i,((j+1)%len(profile))*n+i,((j+1)%len(profile))*n+(i+1)%n,j*n+(i+1)%n) for j in range(len(profile)) for i in range(n)]
 guard=mesh('Fixed_ice_nozzle',v,f,'underwater')
 for poly in guard.data.polygons:poly.use_smooth=True

def ice_blade(x,z,angle,central):
 # Four radial sections give the blade a swept tip and progressive twist.
 v=[]
 for r,s,c,t in [(.30,-.08,.15,.24),(.85,.05,.46,.19),(1.60,.26,.39,.12),(2.03,.40,.08,.05)]:
  for offset,axial in [(-c,-t),(c,-t*.18),(c,t),(-c,t*.48)]:
   v.append((x+r*math.cos(angle)-(s+offset)*math.sin(angle),-73.5+axial,z+r*math.sin(angle)+(s+offset)*math.cos(angle)))
 f=[(0,3,2,1),(12,13,14,15)]+[(i*4+j,i*4+(j+1)%4,(i+1)*4+(j+1)%4,(i+1)*4+j) for i in range(3) for j in range(4)]
 mesh('Centre_ice_propeller_blade' if central else 'Ice_strengthened_propeller_blade',v,f,'brass')

def foil(n,x,profile,mat):
 v=[(x+t*sgn,y,z) for sgn in [-1,1] for y,z,t in profile]
 k=len(profile);f=[tuple(reversed(range(k))),tuple(range(k,2*k))]
 f += [(i,(i+1)%k,(i+1)%k+k,i+k) for i in range(k)]
 return mesh(n,v,f,mat)

for x,shaft_z,rudder_z in [(-5,-6.4,-4.7),(0,-7,-5.3),(5,-6.4,-4.7)]:
 central=(x==0)
 cyl('Centre_shaft' if central else 'Shaft_strut',(x,-66,shaft_z),.37,14.8,'darkgrey',16,(math.pi/2,0,0))
 cyl('Centre_propeller_hub' if central else 'Propeller_hub',(x,-73.5,shaft_z),.56,1.82,'brass',20,(math.pi/2,0,0))
 screw_guard(x,shaft_z)
 for i in range(5):ice_blade(x,shaft_z,i*math.tau/5,central)
 for side in [-1,1]:
  beam('Nozzle_V_bracket',(x+side*1.45,-73.02,shaft_z+1.81),(x+side*1.75,-70.0,-2.0),.20,'underwater',12)
 foil('Centre_rudder' if central else 'Ice_protected_rudder',x,[(-75.55,rudder_z+1.67,.13),(-78.16,rudder_z+1.50,.13),(-78.53,rudder_z-1.60,.07),(-77.76,rudder_z-1.99,.10),(-75.77,rudder_z-1.89,.22)],'underwater')
 cyl('Fixed_rudder_post',(x,-76.98,(rudder_z+2.60)/2),.29,1.0-(rudder_z+1.60),'darkgrey',16)
 foil('Fixed_after_ice_horn',x,[(-77.92,2.2,.40),(-79.45,3.0,.23),(-79.60,rudder_z+.12,.12),(-78.95,rudder_z-.08,.20),(-78.82,rudder_z+1.78,.29)],'underwater')
# The tapered skeg overlaps the keel and limits a deep ride-up in the design.
foil('Forefoot_ice_skeg',0,[(46,-8.12,.09),(56,-6.35,.70),(64,-4.27,.55),(69,-2.05,.15),(66,-4.98,.24),(57,-7.67,.44),(50,-8.70,.20)],'underwater')

# RHIB handling bays and weather-protected rescue boats.
for side in [-1,1]:
 x=side*11.7;y=-1.5
 cube('RHIB_cradle',(x,y,8.2),(1.8,8.6,.55),'darkgrey')
 sphere('RHIB_inflatable_tubes',(x,y,9),1,'black',(.95,4,.6))
 cube('RHIB_interior',(x,y,9.25),(1.2,6.3,.2),'lightgrey')
 cube('RHIB_console',(x,y+.4,9.9),(.65,.85,.95),'darkgrey')
 for yy in [-4,1.0]:
  beam('RHIB_davit_post',(side*13.3,yy,7.85),(side*13.3,yy,12.5),.18)
  beam('RHIB_davit_boom',(side*13.3,yy,12.5),(side*11.3,yy,12.5),.18)
  beam('RHIB_hoist_wire',(side*11.3,yy,12.5),(side*11.3,yy,9.5),.025,'black',6)
 # Orange enclosed lifeboats sit in roof-edge davits.
 x=side*11.8;y=14
 sphere('Enclosed_lifeboat',(x,y,15),1,'safety',(1.2,4.4,1.25))
 cube('Lifeboat_wheelhouse',(x,y+.6,16.1),(1.3,2.4,.65),'safety')
 for yy in [11,17]:beam('Lifeboat_davit',(side*10.3,yy,13.9),(side*12.7,yy,16.6),.11,'lightgrey')
 for yy in [12.7,14,15.3]:cube('Lifeboat_side_glass',(side*12.65,yy,15.8),(.05,.8,.35),'glass',.02)

# Integrated elevated defensive mounts, deliberately no missiles or offensive weapons.
mounts=[]
def gun30():
 cyl('Gun30_base',(0,57,8.15),1.25,.6,'darkgrey',24)
 o=taper('GunYaw',55.7,58.2,8.45,10.15,1.25,.9,'lightgrey')
 o=cyl('GunBarrel',(0,60.0,9.7),.11,4.0,'darkgrey',12,(math.pi/2,0,0))
 cyl('GunBarrel_muzzle',(0,62.05,9.7),.16,.18,'black',12,(math.pi/2,0,0))
 mounts.append({'id':'Gun30','yaw_object':'GunYaw','barrel_object':'GunBarrel','native_base_m':[0,8.45,57],'native_barrel_pivot_m':[0,9.7,58.0],'supported_by':'Gun30_base','role':'25mm warning and patrol gun'})
gun30()
for idx,(side,y) in enumerate([(-1,28),(1,-24)],1):
 x=side*11
 # rectangular platform physically overlaps the side of superstructure/hangar.
 cube('CIWS_sponson_'+str(idx),(x,y,13.55),(5.0,5.6,.65),'hull')
 cube('CIWS_support_'+str(idx),(x,y,10.55),(3.2,4.1,5.5),'hull')
 cyl('CIWS_foundation_'+str(idx),(x,y,14.05),1.1,.35,'darkgrey',24)
 cyl('CIWSYaw'+str(idx),(x,y,14.9),.95,1.4,'lightgrey',20)
 cube('CIWSYaw'+str(idx)+'_equipment',(x,y,15.4),(1.5,1.6,1.35),'lightgrey')
 sphere('CIWSYaw'+str(idx)+'_radome',(x,y-.1,17.0),.75,'white',(1,1,1.25))
 # Foreward barrel for native animation plus six discrete outer barrels.
 cyl('CIWSBarrel'+str(idx),(x,y+1.4,15.55),.19,2.8,'darkgrey',12,(math.pi/2,0,0))
 for a in range(6):
  t=a*math.tau/6;cyl('CIWSBarrel'+str(idx)+'_gatling',(x+.12*math.cos(t),y+1.4,15.55+.12*math.sin(t)),.045,2.8,'black',6,(math.pi/2,0,0))
 mounts.append({'id':'CIWS'+str(idx),'yaw_object':'CIWSYaw'+str(idx),'barrel_object':'CIWSBarrel'+str(idx),'native_base_m':[x,14.22,y],'native_barrel_pivot_m':[x,15.55,y],'supported_by':'CIWS_foundation_'+str(idx),'role':'Phalanx 20mm close-in defence; masked arcs require in-game test'})
mg_index=0
for side in [-1,1]:
 for y in [42,-38]:
  mg_index+=1
  x=side*(10.1 if y>0 else 11.7);z=7.83
  cyl('M2_pedestal',(x,y,z+.6),.11,1.2,'darkgrey',12)
  cube('MGYaw'+str(mg_index),(x,y,z+1.22),(.18,.7,.2),'black')
  beam('MGBarrel'+str(mg_index),(x,y+.2,z+1.22),(x,y+1.35,z+1.22),.038,'black')
  mounts.append({'id':'MG'+str(mg_index),'yaw_object':'MGYaw'+str(mg_index),'barrel_object':'MGBarrel'+str(mg_index),'native_base_m':[x,z+1.22,y],'native_barrel_pivot_m':[x,z+1.22,y+.2],'supported_by':'WeatherDeck_continuous','role':'.50cal patrol defence'})

# Flush shell hawse fittings, a raised sheer and sheltered mooring stations.
for side in [-1,1]:
 x=side*4;y=68
 cyl('Anchor_windlass',(x,y,deck_at(y)+.54),.62,1.05,'darkgrey',16)
 beam('Anchor_chain',(x,69,deck_at(69)+.10),(side*5.13,73,deck_at(73)+.10),.10,'black',8)
 for name,y,z,size in [('Recessed_hawse_plate',69.5,5.45,(.11,.76,.49)),('Anchor_recess',69.5,5.45,(.135,.55,.32))]:
  sphere(name,(side*hull_breadth(y,z),y,z),1,'darkgrey' if name.endswith('plate') else 'black',size)
 for z1,z2,ya,yb in [(5.40,4.32,69.50,69.31),(4.30,4.67,69.31,68.72),(4.30,4.68,69.31,69.83)]:
  beam('Housed_anchor',(side*(hull_breadth(ya,z1)+.07),ya,z1),(side*(hull_breadth(yb,z2)+.07),yb,z2),.102,'darkgrey',10)
 ys=[44,50,57,63,68,71,73.5,75.5,77,78.4,79.35]
 run=[(side*(section_at(y)[-1][0]-.30),y,deck_at(y)+.02) for y in ys]
 v=[(x+side*offset,y,z+h) for x,y,z in run for offset,h in [(0,0),(0,1.08),(-.13,1.12),(-.10,0)]]
 f=[(j*4+i,j*4+(i+1)%4,(j+1)*4+(i+1)%4,(j+1)*4+i) for j in range(len(run)-1) for i in range(4)]
 f.extend([(3,2,1,0),tuple(4*(len(run)-1)+i for i in range(4))])
 mesh('Forecastle_weather_bulwark',v,f,'hull')
 for p,q in zip(run,run[1:]):
  beam('Forecastle_bulwark_cap',(p[0],p[1],p[2]+1.10),(q[0],q[1],q[2]+1.10),.075,'lightgrey',8)
 rail('Foredeck_rail',[(side*13.4,37,7.83),(side*13.55,44,7.83)])
 rail('Middeck_rail',[(side*13.3,-40,7.83),(side*13.3,-8,7.83)])

# Forward/downward ice observation lights carried on the bridge brow.
for side in [-1,1]:
 x=side*8.7;y=35.3
 cyl('Ice_searchlight_pedestal',(x,y,22.95),.30,.54,'darkgrey',16)
 for dx in [-.37,.37]:
  beam('Ice_searchlight_yoke',(x+dx*.65,y,23.14),(x+dx,y,23.54),.065,'darkgrey',10)
 lamp=cyl('Ice_searchlight_housing',(x,y,23.51),.40,.70,'darkgrey',24)
 lamp.rotation_euler.x=math.pi/2-.16
 lens=cyl('Ice_searchlight_lens',(x,y+.33,23.45),.34,.045,'white',24)
 lens.rotation_euler=lamp.rotation_euler
 cube('Ice_searchlight_hood',(x,y+.20,23.86),(.80,.67,.08),'lightgrey',.03)

# Mast, exhaust for emergency generator only, rescue fittings.
cube('Emergency_generator_casing',(0,7,15.2),(8.4,8.5,2.8),'lightgrey')
cube('Emergency_generator_vent',(0,6,17.0),(4,4,.5),'darkgrey')
for side in [-1,1]:
 for z in [15,15.4,15.8,16.2]:cube('Generator_vent_louver',(side*4.22,7,z),(.03,5,.14),'black',0)
cyl('Auxiliary_exhaust',(2.3,7,18.6),.38,3.0,'darkgrey',12)
cube('Mast_base',(0,20,23.1),(5.4,5.4,1.0),'hull')
taper('Main_mast',18,22,23.6,31.5,1.8,.9,'lightgrey')
cube('Mast_crossarm',(0,20,29.0),(14,.65,.6),'lightgrey')
for side in [-1,1]:
 cyl('Mast_navigation_light',(side*6.4,20,29.5),.15,.4,'nav_red' if side<0 else 'nav_green',12)
 beam('Mast_support',(side*1.7,20,24),(side*6.2,20,28.8),.1,'lightgrey')
 for y in [15,31]:beam('Whip_antenna',(side*8.6,y,22.6),(side*8.6,y,27.6),.027,'darkgrey',6)
 # a single side-access crane with boom stowed along hull; no exposed military VLS.
 x=side*9.1;y=-9
 cyl('Cargo_crane_pedestal',(x,y,16.0),.55,1.0,'yellow',16)
 cyl('Cargo_crane_knuckle',(x,y,17.0),.4,1.1,'yellow',12)
 beam('Cargo_crane_stowed_boom',(x,y,17.2),(x,y+7.6,18),.23,'yellow')
 beam('Cargo_crane_wire',(x,y+7.6,18),(x,y+7.6,15.5),.027,'black',6)
 cube('Crane_hook',(x,y+7.6,15.4),(.16,.3,.3),'darkgrey',.03)
cube('Rescue_medical_service_module',(0,-6,8.9),(6.0,3.0,2.1),'module')
cube('Module_roof',(0,-6,10.0),(6.2,3.2,.15),'lightgrey')

# Era modules: identical hull/interfaces, sensibly period-specific silhouettes.
for yr in [2000,2010,2020]:
 CUR=ERAS[yr]
 cube('M'+str(yr)+'_radar_pedestal',(0,20,32.0),(1.5,1.5,1),'darkgrey')
 if yr==2000:
  cube('M2000_surface_radar',(0,20,32.9),(7.5,.55,.8),'lightgrey')
  for x in [-3,-2,-1,0,1,2,3]:cube('M2000_radar_array_slot',(x,19.7,32.9),(.08,.05,.6),'darkgrey',0)
  sphere('M2000_satcom',(6.2,19,24.1),1.0,'white')
  cube('M2000_optical_director',(-6.2,19,23.55),(1.2,1.2,1.4),'darkgrey')
  cube('M2000_work_module',(0,-19,16.8),(6.1,3.2,2.3),'module')
 elif yr==2010:
  cube('M2010_surface_radar',(0,20,33.0),(5.8,.8,1.2),'lightgrey')
  sphere('M2010_satcom1',(6.3,18,24.4),1.25,'white')
  sphere('M2010_satcom2',(-6.3,18,24.1),1.0,'white')
  sphere('M2010_EOIR',(0,33,23.55),.7,'darkgrey');cube('M2010_EO_window',(0,33.66,23.55),(.55,.08,.4),'glass')
  cube('M2010_hydrographic_module',(0,-19,16.8),(6.1,3.2,2.3),'module')
  cyl('M2010_science_radome',(0,-19,18.3),.8,.7,'white',20)
 else:
  cyl('M2020_compact_radar',(0,20,33),1.1,1.9,'lightgrey',6)
  for side in [-1,1]:
   sphere('M2020_multiband_satcom',(side*6.5,18,24.5),1.4,'white')
   sphere('M2020_EOIR',(side*8.7,31,23.5),.6,'darkgrey')
   cube('M2020_EOIR_window',(side*8.7,31.57,23.5),(.45,.06,.32),'glass')
   cyl('M2020_Lowprofile_antenna',(side*4.2,29,23.1),.85,.4,'white',20)
  cube('M2020_UAV_science_module',(0,-19,16.8),(6.1,3.2,2.3),'module')
  cube('M2020_module_solar_panel',(0,-19,18.03),(5.5,2.8,.09),'blue',0)
  for i in range(5):cube('M2020_panel_cell_divider',(-2.2+i*1.1,-19,18.085),(.035,2.8,.01),'lightgrey',0)
  cube('M2020_small_UAV_landing_mat',(0,-29,15.75),(5,5,.1),'heli')
  ring('M2020_UAV_landing_ring',(0,-29,15.82),1.6,width=.13)
 CUR=ROOT

# Pennant figures are projected onto the shell after conversion to triangles.
for side in [-1,1]:
 text('Hull_number_A190','A190',(side*14.0,44,4.40),1.65,'white',(math.pi/2,0,side*math.pi/2))
 for n,z in enumerate([-.8,-.4,0,.4,.8,1.2,1.6,2.0]):
  y=38
  x=hull_breadth(y,z)+.035
  cube('Draft_mark',(side*x,y,z),(.04,.48 if n%2==0 else .25,.075),'white',0)
 cyl('Unit_badge',(side*11.99,26,13),.65,.035,'blue',24,(0,math.pi/2,0))
text('Stern_name','RIMEHAVEN',(0,-80.025,5.1),.84,'white',(math.pi/2,0,0))

beam('Stern_flagpole',(0,-77.5,7.85),(0,-77.5,12.3),.065,'lightgrey')
mesh('Australian_blue_ensign_stylised',[(0,-77.5,12.1),(2.8,-77.2,11.9),(2.8,-77.2,10.65),(0,-77.5,10.8)],[(0,1,2,3)],'blue')
# mast halyard and cross as a restrained Australian identity cue.
cube('Flag_union_horizontal',(.65,-77.49,11.6),(1.3,.035,.16),'white',0)
cube('Flag_union_vertical',(.65,-77.49,11.6),(.13,.035,.9),'white',0)
for x,z in [(1.8,11.6),(2.35,11.4),(2.1,10.95),(1.65,10.9)]:sphere('Flag_southern_cross',(x,-77.25,z),.07,'white')

# Convert text to geometry to keep every source export self-contained.
for o in list(bpy.context.scene.objects):
 if o.type=='FONT':bpy.context.view_layer.objects.active=o;o.select_set(True);bpy.ops.object.convert(target='MESH');o.select_set(False)

# Project each pennant letter onto the flared topside so both numbers follow the
# shell and stay inside its moulded maximum beam.
bpy.context.view_layer.update()
for obj in list(ROOT.objects):
 if obj.name.startswith('Hull_number_A190'):
  inverse=obj.matrix_world.inverted()
  side=1 if obj.location.x>0 else -1
  for vertex in obj.data.vertices:
   point=obj.matrix_world@vertex.co
   point.x=side*(hull_breadth(point.y,point.z)+.046)+.65*(point.x-obj.location.x)
   vertex.co=inverse@point
def era_visibility(yr):
 for y,c in ERAS.items():c.hide_render=y!=yr;c.hide_viewport=y!=yr
def visible_objects(yr):return list(ROOT.objects)+list(ERAS[yr].objects)
def native(v):return (v.x,v.z,v.y)
def export_obj(yr):
 objs=visible_objects(yr);objpath=OUT/('aurora_'+str(yr)+'.obj');mtlpath=OUT/('aurora_'+str(yr)+'.mtl')
 with mtlpath.open('w') as f:
  for n,m in MAT.items():
   c=m.diffuse_color;f.write(f'newmtl {n}\nKa {c[0]:.4f} {c[1]:.4f} {c[2]:.4f}\nKd {c[0]:.4f} {c[1]:.4f} {c[2]:.4f}\nKs 0.05 0.05 0.05\nNs 20\nd 1\nillum 2\n\n')
 deps=bpy.context.evaluated_depsgraph_get();vi=1;ni=1
 with objpath.open('w') as f:
  f.write('# HMAS Rimehaven source: metres, X starboard Y up Z forward\nmtllib '+mtlpath.name+'\n')
  for o in objs:
   if o.type!='MESH':continue
   eo=o.evaluated_get(deps);me=eo.to_mesh();me.calc_loop_triangles();f.write('\no '+o.name.replace(' ','_')+'\n')
   for v in me.vertices:
    p=eo.matrix_world@v.co;x,y,z=native(p);f.write(f'v {x:.6f} {y:.6f} {z:.6f}\n')
   # native axis swap changes handedness, so reverse triangle order.
   for tri in me.loop_triangles:
    ma=me.materials[tri.material_index] if len(me.materials)>tri.material_index else MAT['hull'];f.write('usemtl '+ma.name+'\n')
    ids=[vi+i for i in reversed(tri.vertices)];f.write('f '+' '.join(map(str,ids))+'\n')
   vi+=len(me.vertices);eo.to_mesh_clear()
 return objpath

# World/camera used only for review renders, excluded from model exports.
scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH'
scene.render.resolution_x=1800;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.world.color=(.19,.23,.28)
scene.display.shading.light='STUDIO';scene.display.shading.studiolight_rotate_z=2.8
scene.display.shading.color_type='MATERIAL';scene.display.shading.show_shadows=True
scene.display.shading.show_cavity=True;scene.display.shading.cavity_type='BOTH';scene.display.shading.curvature_ridge_factor=1.4;scene.display.shading.curvature_valley_factor=1.1
scene.display.shading.show_specular_highlight=True;scene.display.shading.background_type='WORLD'
scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
bpy.ops.object.camera_add();cam=bpy.context.object;cam.name='REVIEW_CAMERA';scene.camera=cam;cam.data.type='ORTHO'
def camera_render(name,loc,target,scale):
 cam.location=loc;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=scale;scene.render.filepath=str(OUT/name);bpy.ops.render.render(write_still=True)
for yr in [2000,2010,2020]:
 era_visibility(yr);export_obj(yr)
 bpy.ops.object.select_all(action='DESELECT')
 for o in visible_objects(yr):o.select_set(True)
 bpy.ops.export_scene.gltf(filepath=str(OUT/('Aurora-'+str(yr)+'.glb')),export_format='GLB',use_selection=True,export_apply=True,export_yup=True)
era_visibility(2020)
camera_render('Aurora-2020-Overview.png',(145,185,100),(0,0,6),188)
camera_render('Aurora-2020-Port-Quarter.png',(-150,-175,90),(0,0,5),188)
camera_render('Aurora-2020-Side.png',(200,0,35),(0,0,6),182)
scene.render.resolution_x=1100;scene.render.resolution_y=1800
camera_render('Aurora-2020-Top.png',(0,-1,240),(0,0,0),183)
scene.render.resolution_x=1800;scene.render.resolution_y=1100
era_visibility(2000);camera_render('Aurora-2000-Overview.png',(145,185,100),(0,0,6),188)
era_visibility(2010);camera_render('Aurora-2010-Overview.png',(145,185,100),(0,0,6),188)
era_visibility(2020)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Aurora-Class-Source.blend'))

# Exact AABBs and attachment supports in native metre axes, for downstream validation.
records=[]
for yr in [2000,2010,2020]:
 for o in visible_objects(yr):
  if o.type!='MESH':continue
  pp=[native(o.matrix_world@Vector(c)) for c in o.bound_box]
  records.append({'era':yr,'object':o.name,'min':[round(min(p[i] for p in pp),5) for i in range(3)],'max':[round(max(p[i] for p in pp),5) for i in range(3)]})
manifest={'name':'HMAS Rimehaven','class':'White Meridian class','fictional':True,'model_version':'0.2.0','units':'metres','native_axes':{'x':'starboard','y':'up','z':'forward'},'hull_length_m':160,'beam_m':29,'design_draft_m':9.5,'design_full_load_tonnes':28000,'design_open_water_knots':18,'design_ice_target':'2 m level ice at 3 knots, unvalidated concept target','era_variants':[2000,2010,2020],'propeller_anchors_m':[[-5,-6.4,-73.5],[0,-7,-73.5],[5,-6.4,-73.5]],'rudder_anchors_m':[[-5,-4.7,-77],[0,-5.3,-77],[5,-4.7,-77]],'propulsion':'Fictional nuclear electric; no reactor internals or verified game nuclear simulation','armament':['1 x 25mm patrol cannon','2 x Phalanx 20mm CIWS','4 x .50cal'], 'mounts':mounts,'bounds':records,'common_hull_objects':len(ROOT.objects),'module_objects':{str(k):len(v.objects) for k,v in ERAS.items()},'limitations':['No ice-structure or stability analysis','No live game test','CIWS physical masking needs in-game test; no claim of gap-free coverage','No missiles or torpedoes','Period modules are prebuilt selectable variants, not proven live in-game refits']}
(OUT/'Aurora-Model-Manifest.json').write_text(json.dumps(manifest,indent=2))
print('RIMEHAVEN_BUILD_COMPLETE',OUT)
