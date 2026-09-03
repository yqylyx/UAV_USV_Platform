<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import type { AlgorithmRuntimeFrame } from '@/types/mission'

const props=defineProps<{frame:AlgorithmRuntimeFrame|null;selectedDeviceCode?:string}>()
const emit=defineEmits<{select:[code:string];placeThreat:[x:number,y:number]}>()
const width=1200,height=620,plot={x:22,y:22,w:1156,h:576}
const histories=reactive<Record<string,Array<{x:number;y:number}>>>({})
const telemetry=reactive({distance:[] as number[],minimumSpacing:[] as number[],stability:[] as number[]})
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
  const points=objects.value.flatMap(item=>[
    {x:item.x,y:item.y},
    ...(histories[item.code]||[]).slice(-160),
  ])
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
const currentStage=computed(()=>String(props.frame?.metrics?.missionStage||props.frame?.phase||''))
const enclosure=computed(()=>['ENCIRCLEMENT','GAP_REPAIR','STABLE_CONTAINMENT','COMPLETED','CAPTURED'].includes(currentStage.value))
const phaseLabel=computed(()=>({ASSIGNMENT:'任务分配',TRANSIT:'航行接近',ESCAPE:'目标逃逸',PURSUIT:'协同追击',INTERCEPT:'加速拦截',BLOCKING:'阻断攻击',ENCIRCLEMENT:'动态围捕',GAP_REPAIR:'动态围捕',STABLE_CONTAINMENT:'稳定闭环',CAPTURED:'围捕完成',GUARDING:'警戒护航',THREAT_DETECTION:'威胁侦测',ESCORTING:'警戒护航',APPROACHING:'威胁侦测',FORMING:'守卫编队形成',ORBITING:'动态护卫',THREAT_RESPONSE:'威胁响应',COMPLETED:'任务完成'}[currentStage.value]||currentStage.value||'等待算法帧'))
const steps=computed(()=>props.frame?.algorithmCode==='ESCORT_GUARD'?['警戒护航','威胁侦测','加速拦截','阻断攻击','动态围捕','稳定闭环','完成']:['目标逃逸','协同追击','截击部署','动态围捕','稳定闭环','完成'])
const phaseIndex=computed(()=>{
  const capture:Record<string,number>={ASSIGNMENT:0,TRANSIT:0,ESCAPE:0,PURSUIT:1,INTERCEPT:2,ENCIRCLEMENT:3,GAP_REPAIR:3,STABLE_CONTAINMENT:4,CAPTURED:5,COMPLETED:5}
  const escort:Record<string,number>={GUARDING:0,ESCORTING:0,THREAT_DETECTION:1,INTERCEPT:2,BLOCKING:3,ENCIRCLEMENT:4,GAP_REPAIR:4,STABLE_CONTAINMENT:5,COMPLETED:6}
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
const latest=(values:number[])=>values.length?values[values.length-1]:undefined
const selectedObject=computed(()=>objects.value.find(item=>item.code.toLowerCase()===props.selectedDeviceCode?.toLowerCase())??null)
const situationJudgement=computed(()=>{
  if(!props.frame)return'等待实时数据'
  if(props.frame.algorithmCode==='ESCORT_GUARD')return ['THREAT_RESPONSE','COMPLETED'].includes(props.frame.phase)?'护航响应已建立':'护航编队运行中'
  return enclosure.value?'包围态势已形成':'包围态势建立中'
})
const metricCards=computed(()=>[
  {key:'uav',title:'UAV 编队质量',value:uavQuality.value===null?'--':`${format(uavQuality.value,0)}%`,tone:'uav'},
  {key:'usv',title:usvQualityLabel.value,value:usvQuality.value===null?'--':`${format(usvQuality.value,0)}%`,tone:'usv'},
  {key:'distance',title:'目标平均距离',value:`${format(latest(telemetry.distance),1)} m`,tone:'neutral'},
  {key:'minimumSpacing',title:'最小水平间距',value:`${format(latest(telemetry.minimumSpacing),1)} m`,tone:'safe'},
  {key:'stability',title:'编队稳定度',value:`${format(latest(telemetry.stability),0)}%`,tone:'neutral'},
])
watch(()=>props.frame?.sequence,()=>{
  if(!props.frame)return
  if(runId!==props.frame.runId){runId=props.frame.runId;Object.keys(histories).forEach(k=>delete histories[k]);telemetry.distance=[];telemetry.minimumSpacing=[];telemetry.stability=[]}
  for(const item of [...props.frame.agents,...visibleTargets.value]){
    const list=histories[item.code]||(histories[item.code]=[]),last=list[list.length-1]
    if(!last||Math.hypot(last.x-item.x,last.y-item.y)>.06)list.push({x:item.x,y:item.y})
    if(list.length>520)list.splice(0,list.length-520)
  }
  if(activeTarget.value&&props.frame.agents.length){
    const agents=props.frame.agents,distances=agents.map(item=>Math.hypot(item.x-activeTarget.value!.x,item.y-activeTarget.value!.y)),pairs:number[]=[]
    for(let i=0;i<agents.length;i++)for(let j=i+1;j<agents.length;j++)pairs.push(Math.hypot(agents[i]!.x-agents[j]!.x,agents[i]!.y-agents[j]!.y))
    const mean=distances.reduce((a,b)=>a+b,0)/distances.length,sd=Math.sqrt(distances.reduce((s,v)=>s+(v-mean)**2,0)/distances.length)
    telemetry.distance.push(mean);telemetry.minimumSpacing.push(pairs.length?Math.min(...pairs):0);telemetry.stability.push(Math.max(0,100-sd/Math.max(mean,1)*150))
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
    <header class="situation-summary">
      <div class="metric-grid">
        <article v-for="item in metricCards" :key="item.key" class="metric-card" :class="item.tone">
          <span>{{ item.title }}</span><strong>{{ item.value }}</strong>
          <small v-if="item.key==='uav'">{{ uavs.length }}/3 数据有效</small>
          <small v-else-if="item.key==='usv'">{{ usvs.length }}/3 数据有效</small>
          <small v-else-if="item.key==='minimumSpacing'">二维水平距离</small>
          <small v-else>实时计算</small>
        </article>
      </div>
    </header>
    <div class="map-stage">
      <aside class="situation-side unit-panel">
        <div class="side-title"><span>作战单元</span><b>{{ objects.length }} 个目标</b></div>
        <dl class="unit-counts">
          <div><dt>UAV</dt><dd>{{ uavs.length }}/3</dd></div>
          <div><dt>USV</dt><dd>{{ usvs.length }}/3</dd></div>
          <div><dt>任务目标</dt><dd>{{ visibleTargets.length }}</dd></div>
        </dl>
        <div class="selected-unit">
          <span>当前观察</span>
          <strong>{{ selectedObject?.code.toUpperCase().replace('_','-') || '点击轨迹设备' }}</strong>
          <template v-if="selectedObject">
            <small>东向 {{ format(selectedObject.x,1) }} m</small>
            <small>北向 {{ format(selectedObject.y,1) }} m</small>
            <small>航向 {{ format(selectedObject.heading,0) }}°</small>
          </template>
        </div>
      </aside>
      <div class="map-shell">
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
        <text v-if="!frame" :x="width/2" :y="height/2" text-anchor="middle" class="waiting">等待实时轨迹数据</text>
        </svg>
      </div>
      <aside class="situation-side target-panel">
        <div class="side-title"><span>态势摘要</span><b>{{ phaseLabel }}</b></div>
        <div class="judgement"><i :class="{ready:enclosure}"/><span>{{ situationJudgement }}</span></div>
        <dl class="target-data">
          <div><dt>实时帧</dt><dd>SEQ {{ frame?.sequence ?? 0 }}</dd></div>
          <div><dt>目标东向</dt><dd>{{ format(activeTarget?.x,1) }} m</dd></div>
          <div><dt>目标北向</dt><dd>{{ format(activeTarget?.y,1) }} m</dd></div>
        </dl>
        <div class="legend">
          <span><i class="uav"/>UAV</span><span><i class="usv"/>USV</span><span><i class="target"/>任务目标</span>
        </div>
      </aside>
    </div>
    <footer class="phase">
      <div class="phase-title"><span>任务阶段</span><b>{{ phaseLabel }}</b></div>
      <div class="arc"><i :style="{width:`${phaseIndex/(steps.length-1)*100}%`}"/></div>
      <ol><li v-for="(step,index) in steps" :key="step" :class="{active:index<=phaseIndex,current:index===phaseIndex}"><i/>{{ step }}</li></ol>
    </footer>
  </section>
</template>

<style scoped>
.situation-hud{display:grid;grid-template-rows:auto minmax(0,1fr) auto;width:100%;height:100%;min-height:560px;overflow:hidden;background:#020c12;color:#e9fbfa}.situation-summary{padding:10px 12px;border-bottom:1px solid #173d47;background:#041720}.phase{display:grid;grid-template-rows:auto 8px auto;align-content:center;min-width:0;padding:8px 18px 10px;border-top:1px solid #173d47;background:#041720}.phase-title{display:flex;align-items:center;justify-content:space-between;margin-bottom:5px}.phase-title span{color:#76a4a9;font-size:9px;letter-spacing:.12em}.phase-title b{color:#56e1ce;font-size:11px}.arc{height:2px;background:#173842}.arc i{display:block;height:100%;background:#5fe6d6;box-shadow:0 0 8px #4ce5d6}.phase ol{display:flex;justify-content:space-between;margin:2px 0 0;padding:0;list-style:none}.phase li{display:grid;justify-items:center;gap:3px;color:#668c91;font-size:8px;white-space:nowrap}.phase li i{width:5px;height:5px;border:1px solid #4a747a;border-radius:50%;background:#06171e}.phase li.active{color:#b9e4e1}.phase li.active i{border-color:#51e4c8;background:#51e4c8}.phase li.current{color:#fff;font-weight:800}.metric-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:7px}.metric-card{display:grid;grid-template-columns:1fr auto;align-content:center;gap:3px 8px;min-width:0;padding:8px 10px;border:1px solid #1f4c57;border-radius:6px;background:#061c25}.metric-card span{overflow:hidden;color:#7fa7ab;font-size:8px;white-space:nowrap;text-overflow:ellipsis}.metric-card strong{grid-row:1/3;grid-column:2;color:#efffff;font-size:14px}.metric-card small{color:#557d82;font-size:8px}.metric-card.uav{border-color:#705f24}.metric-card.uav strong{color:#ffc83d}.metric-card.usv{border-color:#70343b}.metric-card.usv strong{color:#ff747c}.metric-card.safe strong{color:#55e6aa}.map-stage{display:grid;grid-template-columns:210px minmax(0,1fr) 210px;gap:10px;min-height:0;padding:10px 12px}.map-shell{position:relative;min-width:0;min-height:0;overflow:hidden;border:1px solid #205966;background:#031821}.map{display:block;width:100%;height:100%}.situation-side{display:flex;min-height:0;flex-direction:column;gap:12px;padding:14px;border:1px solid #194650;background:linear-gradient(180deg,#061c25,#04151d)}.side-title{display:grid;gap:3px;padding-bottom:9px;border-bottom:1px solid #173e47}.side-title span{color:#58d6e2;font-size:9px;letter-spacing:.14em}.side-title b{color:#e9fbfa;font-size:12px}.unit-counts,.target-data{display:grid;gap:6px;margin:0}.unit-counts div,.target-data div{display:flex;align-items:center;justify-content:space-between;padding:8px;border:1px solid #163b44;background:#071f28}.unit-counts dt,.target-data dt{color:#6f989d;font-size:9px}.unit-counts dd,.target-data dd{margin:0;color:#e4faf7;font-size:11px;font-weight:800}.selected-unit{display:grid;gap:7px;margin-top:auto;padding:11px;border:1px solid #28555f;background:#08232d}.selected-unit span{color:#6f999e;font-size:9px}.selected-unit strong{color:#5ce3d6;font-size:14px}.selected-unit small{color:#9ababc;font-size:9px}.judgement{display:flex;align-items:center;gap:8px;padding:9px;border:1px solid #234d57;background:#08212a;color:#d8f1ef;font-size:10px}.judgement i{width:7px;height:7px;border-radius:50%;background:#ffd064;box-shadow:0 0 8px #ffd06488}.judgement i.ready{background:#55e6aa;box-shadow:0 0 8px #55e6aa88}.legend{display:grid;gap:8px;margin-top:auto;padding-top:10px;border-top:1px solid #173e47}.legend span{display:flex;align-items:center;gap:8px;color:#89adb0;font-size:9px}.legend i{width:8px;height:8px;border-radius:50%}.legend .uav{background:#ffc83d}.legend .usv{background:#ff646d}.legend .target{background:#3fc9f2}.water{fill:#031821;stroke:#23616e}.route{fill:none;stroke:#45d6e8;stroke-width:2;stroke-dasharray:8 6}.trail{fill:none;stroke-width:1.8}.trail.old{opacity:.18}.trail.recent{opacity:.84}.uav-form{fill:#ffc83d0b;stroke:#ffc83d;stroke-width:1.5;stroke-dasharray:7 5}.usv-form{fill:#ff646d09;stroke:#ff646d;stroke-width:1.5;stroke-dasharray:7 5}.marker{cursor:pointer}.marker text{font-size:10px;font-weight:800;paint-order:stroke;stroke:#020b11;stroke-width:3px}.marker.selected circle{stroke:#fff;stroke-width:2.5}.waiting{fill:#6f999f;font-size:15px}
@media(max-width:1280px){.metric-grid{grid-template-columns:repeat(5,minmax(100px,1fr))}.map-stage{grid-template-columns:170px minmax(0,1fr) 170px}.situation-side{padding:10px}.situation-hud{min-height:620px}}
@media(max-width:980px){.map-stage{grid-template-columns:1fr}.situation-side{display:none}}
@media(max-width:900px){.metric-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.situation-hud{min-height:680px}}
</style>
