<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import type { AlgorithmRuntimeFrame } from '@/types/mission'

const props=defineProps<{frame:AlgorithmRuntimeFrame|null;missionName:string;selectedDeviceCode?:string}>()
const emit=defineEmits<{select:[code:string];placeThreat:[x:number,y:number]}>()
const width=1200,height=620,plot={x:28,y:46,w:1144,h:542}
const histories=reactive<Record<string,Array<{x:number;y:number}>>>({})
const telemetry=reactive({distance:[] as number[],spacing:[] as number[],stability:[] as number[]})
let runId:number|null=null

const visibleTargets=computed(()=>props.frame?.targets.filter(item=>props.frame?.algorithmCode==='ESCORT_GUARD'
  ? item.type!=='CAPTURE_TARGET'
  : item.type!=='ESCORT_TARGET'&&item.type!=='THREAT_TARGET')||[])
const objects=computed(()=>props.frame?[...props.frame.agents,...visibleTargets.value]:[])
const uavs=computed(()=>props.frame?.agents.filter(item=>item.type==='UAV')||[])
const usvs=computed(()=>props.frame?.agents.filter(item=>item.type==='USV')||[])
const captureTarget=computed(()=>props.frame?.targets.find(item=>item.type==='CAPTURE_TARGET'))
const activeTarget=computed(()=>props.frame?.targets.find(item=>item.type===(props.frame?.algorithmCode==='ESCORT_GUARD'?'ESCORT_TARGET':'CAPTURE_TARGET')))
const bounds=computed(()=>{
  const points=objects.value.flatMap(item=>[{x:item.x,y:item.y},...(histories[item.code]||[])])
  if(!points.length)return{minX:-80,maxX:80,minY:-48,maxY:48}
  let minX=Math.min(...points.map(p=>p.x)),maxX=Math.max(...points.map(p=>p.x))
  let minY=Math.min(...points.map(p=>p.y)),maxY=Math.max(...points.map(p=>p.y))
  const cx=(minX+maxX)/2,cy=(minY+maxY)/2
  let spanX=Math.max(120,maxX-minX+38),spanY=Math.max(80,maxY-minY+32)
  const aspect=plot.w/plot.h
  if(spanX/spanY>aspect)spanY=spanX/aspect;else spanX=spanY*aspect
  minX=cx-spanX/2;maxX=cx+spanX/2;minY=cy-spanY/2;maxY=cy+spanY/2
  return{minX,maxX,minY,maxY}
})
const sx=(x:number)=>plot.x+(x-bounds.value.minX)/(bounds.value.maxX-bounds.value.minX)*plot.w
const sy=(y:number)=>plot.y+plot.h-(y-bounds.value.minY)/(bounds.value.maxY-bounds.value.minY)*plot.h
const color=(type:string)=>type==='UAV'?'#ffc83d':type==='USV'?'#ff646d':type==='ESCORT_TARGET'?'#54e6aa':'#3fc9f2'
const label=(item:{code:string;type:string})=>item.type==='CAPTURE_TARGET'?'围捕目标':item.type==='ESCORT_TARGET'?'护航目标':item.type==='THREAT_TARGET'?'威胁目标':item.code.toUpperCase().replace('_','-')
const path=(code:string,recent=false)=>{
  const points=histories[code]||[],source=recent?points.slice(-80):points
  return source.map((point,index)=>`${index?'L':'M'} ${sx(point.x)} ${sy(point.y)}`).join(' ')
}
const routePath=computed(()=>props.frame?.route.map((point,index)=>`${index?'L':'M'} ${sx(point[0]||0)} ${sy(point[1]||0)}`).join(' ')||'')
const polygon=(items:Array<{x:number;y:number}>)=>items.map(item=>`${sx(item.x)},${sy(item.y)}`).join(' ')
const ringRadius=computed(()=>captureTarget.value&&usvs.value.length?usvs.value.reduce((sum,item)=>sum+Math.hypot(item.x-captureTarget.value!.x,item.y-captureTarget.value!.y),0)/usvs.value.length*plot.w/(bounds.value.maxX-bounds.value.minX):0)
const enclosure=computed(()=>['ENCIRCLEMENT','CAPTURED'].includes(props.frame?.phase||''))
const phaseLabel=computed(()=>({ASSIGNMENT:'任务分配',TRANSIT:'航行接近',ENCIRCLEMENT:'形成围捕',CAPTURED:'围捕完成',ESCORTING:'正常护航',APPROACHING:'威胁接近',FORMING:'守卫编队形成',ORBITING:'动态护卫',THREAT_RESPONSE:'威胁响应',COMPLETED:'任务完成'}[props.frame?.phase||'']||props.frame?.phase||'等待算法帧'))
const steps=computed(()=>props.frame?.algorithmCode==='ESCORT_GUARD'?['任务分配','编队形成','正常护航','威胁接近','威胁响应','任务完成']:['任务分配','航行接近','态势展开','形成围捕','约束收敛','围捕完成'])
const phaseIndex=computed(()=>{
  const capture:Record<string,number>={ASSIGNMENT:0,TRANSIT:1,ENCIRCLEMENT:3,CAPTURED:5}
  const escort:Record<string,number>={ASSIGNMENT:0,FORMING:1,ESCORTING:2,ORBITING:2,APPROACHING:3,THREAT_RESPONSE:4,COMPLETED:5}
  const indexes=props.frame?.algorithmCode==='ESCORT_GUARD'?escort:capture
  return indexes[props.frame?.phase||'']??0
})
const format=(v:number|undefined,d=1)=>Number.isFinite(v)?Number(v).toFixed(d):'--'
function quality(items:Array<{x:number;y:number}>,target?:{x:number;y:number}){
  if(items.length<3)return null
  const values=target?items.map(item=>Math.hypot(item.x-target.x,item.y-target.y)):[Math.hypot(items[0]!.x-items[1]!.x,items[0]!.y-items[1]!.y),Math.hypot(items[1]!.x-items[2]!.x,items[1]!.y-items[2]!.y),Math.hypot(items[2]!.x-items[0]!.x,items[2]!.y-items[0]!.y)]
  const mean=values.reduce((a,b)=>a+b,0)/values.length,sd=Math.sqrt(values.reduce((s,v)=>s+(v-mean)**2,0)/values.length)
  return Math.max(0,Math.min(100,100-sd/Math.max(mean,1)*180))
}
const uavQuality=computed(()=>quality(uavs.value))
const usvQuality=computed(()=>quality(usvs.value,activeTarget.value))
const usvQualityLabel=computed(()=>props.frame?.algorithmCode==='ESCORT_GUARD'?'USV 护卫环质量':'USV 环形围捕质量')
function spark(values:number[]){
  if(values.length<2)return''
  const min=Math.min(...values),max=Math.max(...values),span=Math.max(.001,max-min)
  return values.map((v,i)=>`${i?'L':'M'} ${i/(values.length-1)*160} ${38-(v-min)/span*38}`).join(' ')
}
watch(()=>props.frame?.sequence,()=>{
  if(!props.frame)return
  if(runId!==props.frame.runId){runId=props.frame.runId;Object.keys(histories).forEach(k=>delete histories[k]);telemetry.distance=[];telemetry.spacing=[];telemetry.stability=[]}
  for(const item of [...props.frame.agents,...visibleTargets.value]){
    const list=histories[item.code]||(histories[item.code]=[]),last=list[list.length-1]
    if(!last||Math.hypot(last.x-item.x,last.y-item.y)>.06)list.push({x:item.x,y:item.y})
    if(list.length>520)list.splice(0,list.length-520)
  }
  if(activeTarget.value&&props.frame.agents.length){
    const agents=props.frame.agents,distances=agents.map(item=>Math.hypot(item.x-activeTarget.value!.x,item.y-activeTarget.value!.y)),pairs:number[]=[]
    for(let i=0;i<agents.length;i++)for(let j=i+1;j<agents.length;j++)pairs.push(Math.hypot(agents[i]!.x-agents[j]!.x,agents[i]!.y-agents[j]!.y))
    const mean=distances.reduce((a,b)=>a+b,0)/distances.length,sd=Math.sqrt(distances.reduce((s,v)=>s+(v-mean)**2,0)/distances.length)
    telemetry.distance.push(mean);telemetry.spacing.push(pairs.reduce((a,b)=>a+b,0)/Math.max(1,pairs.length));telemetry.stability.push(Math.max(0,100-sd/Math.max(mean,1)*150))
    for(const values of Object.values(telemetry))if(values.length>72)values.splice(0,values.length-72)
  }
},{immediate:true})

function placeThreat(event:MouseEvent){
  if(props.frame?.algorithmCode!=='ESCORT_GUARD')return
  const svg=event.currentTarget as SVGSVGElement,matrix=svg.getScreenCTM();if(!matrix)return
  const p=svg.createSVGPoint();p.x=event.clientX;p.y=event.clientY;const local=p.matrixTransform(matrix.inverse())
  if(local.x<plot.x||local.x>plot.x+plot.w||local.y<plot.y||local.y>plot.y+plot.h)return
  emit('placeThreat',bounds.value.minX+(local.x-plot.x)/plot.w*(bounds.value.maxX-bounds.value.minX),bounds.value.minY+(plot.y+plot.h-local.y)/plot.h*(bounds.value.maxY-bounds.value.minY))
}
</script>

<template>
  <section class="situation-hud">
    <svg class="map" :viewBox="`0 0 ${width} ${height}`" @dblclick="placeThreat">
      <defs><pattern id="hud-grid" width="64" height="64" patternUnits="userSpaceOnUse"><path d="M64 0H0V64" fill="none" stroke="#3a91a3" stroke-opacity=".14"/></pattern></defs>
      <rect :x="plot.x" :y="plot.y" :width="plot.w" :height="plot.h" class="water"/><rect :x="plot.x" :y="plot.y" :width="plot.w" :height="plot.h" fill="url(#hud-grid)"/>
      <path v-if="routePath" :d="routePath" class="route"/>
      <polygon v-if="frame?.algorithmCode==='GB_SFLA_CS'&&uavs.length===3&&enclosure" :points="polygon(uavs)" class="uav-form"/>
      <circle v-if="frame?.algorithmCode==='GB_SFLA_CS'&&usvs.length===3&&captureTarget&&enclosure" :cx="sx(captureTarget.x)" :cy="sy(captureTarget.y)" :r="ringRadius" class="usv-form"/>
      <g v-for="item in objects" :key="item.code">
        <path :d="path(item.code)" :stroke="color(item.type)" class="trail old"/><path :d="path(item.code,true)" :stroke="color(item.type)" class="trail recent"/>
        <g class="marker" :class="{selected:item.code.toLowerCase()===selectedDeviceCode?.toLowerCase()}" @click.stop="emit('select',item.code.toLowerCase())">
          <circle :cx="sx(item.x)" :cy="sy(item.y)" :r="item.type.includes('TARGET')?7:5" :fill="color(item.type)"/>
          <line :x1="sx(item.x)" :y1="sy(item.y)" :x2="sx(item.x)+Math.cos(item.heading*Math.PI/180)*14" :y2="sy(item.y)-Math.sin(item.heading*Math.PI/180)*14" :stroke="color(item.type)"/>
          <text :x="sx(item.x)+10" :y="sy(item.y)-10" :fill="color(item.type)">{{ label(item) }}</text>
        </g>
      </g>
      <text v-if="!frame" :x="width/2" :y="height/2" text-anchor="middle" class="waiting">等待真实算法轨迹帧</text>
    </svg>
    <div class="caption"><span>COOPERATIVE SITUATION</span><b>{{ missionName }}</b></div>
    <div class="phase"><div class="arc"><i :style="{width:`${phaseIndex/(steps.length-1)*100}%`}"/></div><ol><li v-for="(step,index) in steps" :key="step" :class="{active:index<=phaseIndex,current:index===phaseIndex}"><i/>{{ step }}</li></ol></div>
    <article class="quality uav"><span>UAV 三角编队质量</span><strong>{{ uavQuality===null?'--':`${format(uavQuality,0)}%` }}</strong><div><i :style="{width:`${uavQuality||0}%`}"/></div><small>{{ uavs.length }}/3 在线</small></article>
    <article class="quality usv"><span>{{ usvQualityLabel }}</span><strong>{{ usvQuality===null?'--':`${format(usvQuality,0)}%` }}</strong><div><i :style="{width:`${usvQuality||0}%`}"/></div><small>{{ usvs.length }}/3 在线</small></article>
    <article v-for="item in [{key:'distance',title:'目标平均距离',unit:'m'},{key:'spacing',title:'设备平均间距',unit:'m'},{key:'stability',title:'编队稳定度',unit:'%'}]" :key="item.key" class="trend" :class="item.key"><span>{{ item.title }}</span><b>{{ format(telemetry[item.key as keyof typeof telemetry][telemetry[item.key as keyof typeof telemetry].length-1],item.key==='stability'?0:1) }} {{ item.unit }}</b><svg viewBox="0 0 160 38"><path :d="spark(telemetry[item.key as keyof typeof telemetry])"/></svg></article>
    <div class="run"><span>RUN ID {{ frame?.runId||'--' }}</span><span>SEQ {{ frame?.sequence||0 }}</span><b>{{ phaseLabel }}</b></div>
  </section>
</template>

<style scoped>
.situation-hud{position:relative;width:100%;height:100%;min-height:560px;overflow:hidden;background:#020c12;color:#e9fbfa}.map{position:absolute;inset:0;width:100%;height:100%}.water{fill:#031821;stroke:#23616e}.route{fill:none;stroke:#45d6e8;stroke-width:2;stroke-dasharray:8 6}.trail{fill:none;stroke-width:1.8}.trail.old{opacity:.18}.trail.recent{opacity:.84}.uav-form{fill:#ffc83d0b;stroke:#ffc83d;stroke-width:1.5;stroke-dasharray:7 5}.usv-form{fill:#ff646d09;stroke:#ff646d;stroke-width:1.5;stroke-dasharray:7 5}.marker{cursor:pointer}.marker text{font-size:10px;font-weight:800;paint-order:stroke;stroke:#020b11;stroke-width:3px}.marker.selected circle{stroke:#fff;stroke-width:2.5}.waiting{fill:#6f999f;font-size:15px}.caption{position:absolute;left:2%;top:3%;display:grid;gap:3px;text-shadow:0 2px 8px #000}.caption span{color:#54d7e9;font-size:9px;letter-spacing:.18em}.caption b{font-size:13px}.phase{position:absolute;left:50%;top:2.5%;width:min(48%,650px);transform:translateX(-50%)}.arc{height:26px;border-top:1px solid #285e69;border-radius:50%}.arc i{display:block;height:1px;background:#5fe6d6;box-shadow:0 0 8px #4ce5d6}.phase ol{display:flex;justify-content:space-between;margin:-20px 0 0;padding:0;list-style:none}.phase li{display:grid;justify-items:center;gap:5px;color:#668c91;font-size:9px}.phase li i{width:6px;height:6px;border:1px solid #4a747a;border-radius:50%;background:#06171e}.phase li.active{color:#b9e4e1}.phase li.active i{border-color:#51e4c8;background:#51e4c8}.phase li.current{color:#fff;font-weight:800}.quality,.trend,.run{position:absolute;border:1px solid #265763;border-radius:8px;background:#041821d9;box-shadow:0 12px 28px #0005;backdrop-filter:blur(7px)}.quality{top:13%;width:165px;padding:11px}.quality.uav{left:2%}.quality.usv{right:2%}.quality span,.trend span{color:#77a6ab;font-size:9px}.quality strong{float:right;color:#eafcfa;font-size:18px}.quality>div{height:3px;margin:13px 0 7px;background:#17343c}.quality>div i{display:block;height:100%;background:#54e6cf;box-shadow:0 0 8px #54e6cf}.quality small{color:#79a1a6}.trend{bottom:3%;width:170px;padding:9px 11px}.trend.distance{left:2%}.trend.spacing{left:50%;transform:translateX(-50%)}.trend.stability{right:2%}.trend b{float:right;font-size:12px}.trend svg{display:block;width:100%;height:38px;margin-top:7px}.trend path{fill:none;stroke:#53dfd3;stroke-width:1.8;filter:drop-shadow(0 0 3px #53dfd3)}.run{right:2%;top:30%;display:grid;gap:7px;padding:9px 11px;font-size:9px}.run span{color:#7ea4a8}.run b{color:#55e6aa}.run span+span{margin-left:0}@media(max-width:1100px){.quality{width:145px}.phase{width:43%}.trend{width:145px}.run{display:none}}@media(max-height:740px){.situation-hud{min-height:500px}.quality{top:15%;padding:8px}.trend{padding:7px 9px}.trend svg{height:26px}}
@media(max-height:850px){.situation-hud{min-height:420px}.quality{top:16%}.trend{bottom:2%}}
</style>
