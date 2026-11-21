'use strict';
(function () {
const MODELS=JSON.parse(document.getElementById('model-data').textContent);
const ERAS={2000:{title:'2000 · Original fit',items:['Conventional navigation and surveillance radar','Original communications and optical lookout fit','Protected working spaces, boats and utility aviation']},2010:{title:'2010 · Patrol refit',items:['Updated radar and communications modules','Expanded electro-optical surveillance fit','Refreshed patrol and rescue mission equipment']},2020:{title:'2020 · Polar surveillance',items:['Modernised sensor and communications geometry','Additional polar surveillance equipment','Updated mission module while retaining light defence']}};
const canvas=document.getElementById('view'),loading=document.getElementById('loading');
let gl=canvas.getContext('webgl',{antialias:true,alpha:false,preserveDrawingBuffer:true});
function showStatic(message) {
    canvas.parentElement.classList.add('fallback');
    loading.hidden = false;
    loading.textContent = message + ' Showing the 2020 hull study.';
    for (const control of document.querySelectorAll('select, input, .views button, .zoom button')) {
        control.disabled = true;
    }
}
if (!gl) {
    showStatic('WebGL is unavailable.');
    return;
}
// The source uses Sea Power's left-handed, Y-up frame. Reflect X so hull
// lettering and port/starboard fixtures display correctly in right-handed WebGL.
const vs=`attribute vec3 aPos;attribute vec3 aNormal;attribute vec3 aColor;attribute float aCategory;uniform mat4 uViewProjection;varying vec3 vNormal;varying vec3 vColor;varying vec3 vPos;varying float vCategory;void main(){vec3 handedness=vec3(-1.0,1.0,1.0);vNormal=aNormal*handedness;vColor=aColor;vPos=aPos*handedness;vCategory=aCategory;gl_Position=uViewProjection*vec4(vPos,1.0);}`;
const fs=`precision mediump float;varying vec3 vNormal;varying vec3 vColor;varying vec3 vPos;varying float vCategory;uniform float uSelected;uniform float uWater;uniform vec3 uEye;void main(){if(uWater>0.5&&vPos.y<-0.03)discard;vec3 n=normalize(vNormal);if(dot(n,uEye-vPos)<0.0)n=-n;float direct=max(dot(n,normalize(vec3(0.7,1.0,0.5))),0.0);float hemi=0.5+0.5*n.y;vec3 color=vColor*(0.45+0.48*direct+0.16*hemi);vec3 eye=normalize(uEye-vPos);float rim=pow(1.0-abs(dot(n,eye)),3.0)*0.07;color+=vec3(rim);if(uSelected>0.0){float hit=1.0-step(0.3,abs(vCategory-uSelected));color=mix(color*0.26,color+vec3(0.08,0.27,0.20),hit);}float fog=clamp((length(uEye-vPos)-230.0)/850.0,0.0,0.36);color=mix(color,vec3(0.22,0.38,0.46),fog);gl_FragColor=vec4(pow(clamp(color,0.0,1.0),vec3(1.0/2.2)),1.0);}`;
function shader(type,source){let s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s}
let program=gl.createProgram();gl.attachShader(program,shader(gl.VERTEX_SHADER,vs));gl.attachShader(program,shader(gl.FRAGMENT_SHADER,fs));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));gl.useProgram(program);
let pos=gl.getAttribLocation(program,'aPos'),normal=gl.getAttribLocation(program,'aNormal'),color=gl.getAttribLocation(program,'aColor'),category=gl.getAttribLocation(program,'aCategory');
let mvp=gl.getUniformLocation(program,'uViewProjection'),selected=gl.getUniformLocation(program,'uSelected'),water=gl.getUniformLocation(program,'uWater'),eyeLoc=gl.getUniformLocation(program,'uEye');
const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);for(let a of[pos,normal,color,category])gl.enableVertexAttribArray(a);gl.vertexAttribPointer(pos,3,gl.FLOAT,false,40,0);gl.vertexAttribPointer(normal,3,gl.FLOAT,false,40,12);gl.vertexAttribPointer(color,3,gl.FLOAT,false,40,24);gl.vertexAttribPointer(category,1,gl.FLOAT,false,40,36);
gl.enable(gl.DEPTH_TEST);gl.disable(gl.CULL_FACE);
let state={theta:1.00,phi:1.17,radius:214,target:[0,6,3],vertices:0,era:'2020',selected:-1,underwater:true};let buffers={};let activeLoad=0;
function multiply(a,b){let o=new Float32Array(16);for(let c=0;c<4;c++)for(let r=0;r<4;r++)for(let k=0;k<4;k++)o[c*4+r]+=a[k*4+r]*b[c*4+k];return o}
function perspective(fovy,aspect,near,far){let f=1/Math.tan(fovy/2),o=new Float32Array(16);o[0]=f/aspect;o[5]=f;o[10]=(far+near)/(near-far);o[11]=-1;o[14]=2*far*near/(near-far);return o}
function normalize(a){let n=Math.hypot(...a)||1;return a.map(x=>x/n)}
function cross(a,b){return[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]}
function dot(a,b){return a.reduce((s,x,i)=>s+x*b[i],0)}
function lookAt(eye,target){let z=normalize(eye.map((x,i)=>x-target[i])),x=normalize(cross([0,1,0],z)),y=cross(z,x);return new Float32Array([x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,eye),-dot(y,eye),-dot(z,eye),1])}
function draw(){let ratio=Math.min(devicePixelRatio||1,2),w=Math.round(canvas.clientWidth*ratio),h=Math.round(canvas.clientHeight*ratio);if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h}gl.viewport(0,0,w,h);gl.clearColor(.74,.81,.83,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);if(!state.vertices)return;let sin=Math.sin(state.phi),radius=state.radius*Math.max(1,1.2/(w/h)),eye=[state.target[0]+radius*sin*Math.sin(state.theta),state.target[1]+radius*Math.cos(state.phi),state.target[2]+radius*sin*Math.cos(state.theta)];let p=perspective(.60,w/h,.5,2500);gl.uniformMatrix4fv(mvp,false,multiply(p,lookAt(eye,state.target)));gl.uniform3fv(eyeLoc,eye);gl.uniform1f(selected,state.selected);gl.uniform1f(water,state.underwater?0:1);gl.drawArrays(gl.TRIANGLES,0,state.vertices)}
async function decode(model){let bytes=Uint8Array.from(atob(model.data),c=>c.charCodeAt(0));let stream=new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate'));return new Uint8Array(await new Response(stream).arrayBuffer())}
async function loadEra(era){let id=++activeLoad;loading.hidden=false;state.era=era;document.getElementById('mode').textContent=era+' configuration';document.getElementById('eraTitle').textContent=ERAS[era].title;document.getElementById('upgrades').replaceChildren(...ERAS[era].items.map(t=>{let e=document.createElement('li');e.textContent=t;return e}));try{if(!buffers[era])buffers[era]=await decode(MODELS[era]);if(id!==activeLoad)return;gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,buffers[era],gl.STATIC_DRAW);state.vertices=MODELS[era].vertices;document.getElementById('geometry').textContent=MODELS[era].triangles.toLocaleString()+' triangles · authored mesh';loading.hidden=true;draw();window.viewerReady=true;window.viewerEra=era;}catch(e){showStatic('The interactive mesh could not load.');console.error(e)}}
function reset(){setView('quarter')}
document.getElementById('era').addEventListener('change',e=>loadEra(e.target.value));document.getElementById('highlight').addEventListener('change',e=>{state.selected=Number(e.target.value);draw()});document.getElementById('underwater').addEventListener('change',e=>{state.underwater=e.target.checked;draw()});document.getElementById('plus').onclick=()=>{state.radius=Math.max(70,state.radius*.84);draw()};document.getElementById('minus').onclick=()=>{state.radius=Math.min(700,state.radius/ .84);draw()};document.getElementById('reset').onclick=reset;
const views = {
    quarter: {theta: 1.00, phi: 1.17, radius: 214, target: [0,6,3]},
    side: {theta: -Math.PI / 2, phi: Math.PI / 2, radius: 236, target: [0,7,0]},
    bow: {theta: -.95, phi: 1.67, radius: 99, target: [0,2,54]},
    stern: {theta: 2.75, phi: 1.83, radius: 92, target: [0,-3,-69]},
    top: {theta: Math.PI / 2, phi: .001, radius: 250, target: [0,1,0]},
};
function setView(name){
    const view = views[name];
    Object.assign(state, view);
    for(const button of document.querySelectorAll('[data-view]')){
        button.setAttribute('aria-pressed', String(button.dataset.view === name));
    }
    if(name === 'bow' || name === 'stern'){
        document.getElementById('underwater').checked = true;
        state.underwater = true;
    }
    draw();
}
for(const button of document.querySelectorAll('[data-view]')){
    button.addEventListener('click', () => setView(button.dataset.view));
}
let points=new Map(),last=null,pinch=null;canvas.addEventListener('pointerdown',e=>{canvas.setPointerCapture(e.pointerId);points.set(e.pointerId,[e.clientX,e.clientY]);last=[e.clientX,e.clientY];pinch=null});canvas.addEventListener('pointermove',e=>{if(!points.has(e.pointerId))return;points.set(e.pointerId,[e.clientX,e.clientY]);if(points.size===2){let p=[...points.values()],d=Math.hypot(p[0][0]-p[1][0],p[0][1]-p[1][1]);if(pinch)state.radius=Math.max(70,Math.min(700,state.radius*pinch/d));pinch=d;last=null;}else if(last){state.theta-=(e.clientX-last[0])*.007;state.phi=Math.max(.035,Math.min(Math.PI-.035,state.phi+(e.clientY-last[1])*.007));last=[e.clientX,e.clientY]}draw()});function up(e){points.delete(e.pointerId);last=null;pinch=null}canvas.addEventListener('pointerup',up);canvas.addEventListener('pointercancel',up);canvas.addEventListener('wheel',e=>{e.preventDefault();state.radius=Math.max(70,Math.min(700,state.radius*Math.exp(e.deltaY*.001)));draw()},{passive:false});canvas.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')state.theta-=.08;else if(e.key==='ArrowRight')state.theta+=.08;else if(e.key==='ArrowUp')state.phi=Math.max(.035,state.phi-.08);else if(e.key==='ArrowDown')state.phi=Math.min(Math.PI-.035,state.phi+.08);else return;e.preventDefault();draw()});new ResizeObserver(draw).observe(canvas);loadEra('2020');

})();
