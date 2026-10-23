import { useEffect, useRef } from 'react'
import { useReducedMotion } from 'framer-motion'
import './flow-background.css'

const vertexSource=`#version 300 es
in vec2 aPosition;
out vec2 vUv;
void main(){vUv=aPosition*.5+.5;gl_Position=vec4(aPosition,0.,1.);}`

const fragmentSource=`#version 300 es
precision highp float;
uniform float uTime;
uniform vec2 uViewport;
in vec2 vUv;
out vec4 outColor;
float hash(vec3 p){p=fract(p*.1031);p+=dot(p,p.yzx+33.33);return fract((p.x+p.y)*p.z);}
float noise(vec2 p){vec2 b=floor(p),f=fract(p);f=f*f*f*(f*(f*6.-15.)+10.);return mix(mix(hash(vec3(b,0.)),hash(vec3(b+vec2(1,0),0.)),f.x),mix(hash(vec3(b+vec2(0,1),0.)),hash(vec3(b+1.,0.)),f.x),f.y);}
float glow(float d,float peak,float shoulder,float edge){if(d<.42)return mix(peak,shoulder,d/.42);return shoulder*(1.-smoothstep(.42,edge,d));}
void main(){vec2 uv=vec2(vUv.x,1.-vUv.y);float t=uTime*.16;bool mobile=uViewport.x<768.;vec2 p=uv*vec2(2.1,1.55);vec2 warp=vec2(noise(p+vec2(t,-t*.4)),noise(p+vec2(7.2,3.1)-t*.6))-.5;vec2 fuv=uv+warp*vec2(.11,.07);vec2 lc=vec2(.44+sin(t-.8)*.31,-.05+sin(t*.7)*.03);vec2 rc=vec2(.58+sin(t+1.6)*.29,-.08+sin(t*.6)*.025);float l=glow(length((fuv-lc)/vec2(mobile?.92:.64,1.)),mobile?.21:.26,mobile?.085:.098,.88);float r=glow(length((fuv-rc)/vec2(mobile?.8:.59,.94)),.2,mobile?.068:.074,.84);vec3 c=mix(vec3(1.),vec3(.68,.85,1.),r);c=mix(c,vec3(.8,.9,1.),l);c=mix(c,vec3(1.),smoothstep(.7,1.,uv.y));outColor=vec4(clamp(c,0.,1.),1.);}`

const compile=(gl:WebGL2RenderingContext,type:number,source:string)=>{const shader=gl.createShader(type);if(!shader)throw new Error('WebGL shader unavailable');gl.shaderSource(shader,source);gl.compileShader(shader);if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS)){const message=gl.getShaderInfoLog(shader)||'WebGL shader failed';gl.deleteShader(shader);throw new Error(message)}return shader}

export function FlowBackground({className=''}:{className?:string}) {
  const canvasRef=useRef<HTMLCanvasElement>(null)
  const reduced=Boolean(useReducedMotion())
  useEffect(()=>{
    const canvas=canvasRef.current
    if(!canvas)return
    const motionPreference=window.matchMedia('(prefers-reduced-motion: reduce)')
    if(reduced){canvas.dataset.motion='still';canvas.dataset.renderer='fallback';return}
    const gl=canvas.getContext('webgl2',{alpha:true,antialias:false,powerPreference:'low-power'})
    if(!gl){canvas.dataset.renderer='fallback';return}
    let program:WebGLProgram|null=null,buffer:WebGLBuffer|null=null,timeUniform:WebGLUniformLocation|null=null,viewportUniform:WebGLUniformLocation|null=null,frame=0,last=0,elapsed=0,visible=false,lost=false
    const stop=()=>{cancelAnimationFrame(frame);frame=0;last=0}
    const draw=()=>{if(!program||lost)return;gl.drawArrays(gl.TRIANGLES,0,3);canvas.dataset.renderer='webgl'}
    const tick=(now:number)=>{frame=requestAnimationFrame(tick);if(now-last<1000/30)return;elapsed+=last?Math.min((now-last)/1000,.1):0;last=now;gl.uniform1f(timeUniform,elapsed);draw()}
    const pageVisible=()=>document.visibilityState==='visible'
    const sync=()=>{stop();const animate=visible&&pageVisible()&&!lost&&!motionPreference.matches;canvas.dataset.motion=animate?'running':'still';if(visible&&pageVisible()&&!lost)draw();if(animate)frame=requestAnimationFrame(tick)}
    const resize=()=>{if(lost||!program)return;const rect=canvas.getBoundingClientRect();if(!rect.width||!rect.height)return;const dpr=Math.min(devicePixelRatio||1,1.5,Math.sqrt(1_200_000/(rect.width*rect.height)));canvas.width=Math.max(1,Math.round(rect.width*dpr));canvas.height=Math.max(1,Math.round(rect.height*dpr));gl.viewport(0,0,canvas.width,canvas.height);gl.uniform2f(viewportUniform,rect.width,rect.height);draw()}
    const onLost=(event:Event)=>{event.preventDefault();lost=true;canvas.dataset.renderer='fallback';sync()}
    const onRestored=()=>{lost=false;setup()}
    const setup=()=>{
      stop();canvas.dataset.renderer='fallback';canvas.dataset.motion='still'
      if(buffer)gl.deleteBuffer(buffer);if(program)gl.deleteProgram(program)
      program=null;buffer=null;timeUniform=null;viewportUniform=null
      let vertex:WebGLShader|null=null,fragment:WebGLShader|null=null,nextProgram:WebGLProgram|null=null,nextBuffer:WebGLBuffer|null=null
      try {
        vertex=compile(gl,gl.VERTEX_SHADER,vertexSource);fragment=compile(gl,gl.FRAGMENT_SHADER,fragmentSource)
        nextProgram=gl.createProgram();if(!nextProgram)throw new Error('WebGL program unavailable')
        gl.attachShader(nextProgram,vertex);gl.attachShader(nextProgram,fragment);gl.linkProgram(nextProgram)
        if(!gl.getProgramParameter(nextProgram,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(nextProgram)||'WebGL link failed')
        nextBuffer=gl.createBuffer();if(!nextBuffer)throw new Error('WebGL buffer unavailable')
        gl.useProgram(nextProgram);gl.bindBuffer(gl.ARRAY_BUFFER,nextBuffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,3,-1,-1,3]),gl.STATIC_DRAW)
        const position=gl.getAttribLocation(nextProgram,'aPosition');gl.enableVertexAttribArray(position);gl.vertexAttribPointer(position,2,gl.FLOAT,false,0,0)
        program=nextProgram;buffer=nextBuffer;timeUniform=gl.getUniformLocation(program,'uTime');viewportUniform=gl.getUniformLocation(program,'uViewport')
        nextProgram=null;nextBuffer=null;resize();sync()
      } catch {
        if(nextBuffer)gl.deleteBuffer(nextBuffer);if(nextProgram)gl.deleteProgram(nextProgram)
      } finally {
        if(vertex)gl.deleteShader(vertex);if(fragment)gl.deleteShader(fragment)
      }
    }
    const ro=new ResizeObserver(resize)
    const io=new IntersectionObserver(([entry])=>{visible=entry.isIntersecting;sync()})
    canvas.addEventListener('webglcontextlost',onLost)
    canvas.addEventListener('webglcontextrestored',onRestored)
    motionPreference.addEventListener('change',sync)
    document.addEventListener('visibilitychange',sync)
    ro.observe(canvas);io.observe(canvas);setup()
    return()=>{stop();ro.disconnect();io.disconnect();motionPreference.removeEventListener('change',sync);document.removeEventListener('visibilitychange',sync);canvas.removeEventListener('webglcontextlost',onLost);canvas.removeEventListener('webglcontextrestored',onRestored);if(buffer)gl.deleteBuffer(buffer);if(program)gl.deleteProgram(program)}
  },[reduced])
  return <span className={`flow-background ${className}`} aria-hidden="true"><canvas ref={canvasRef} data-renderer="fallback"/></span>
}
