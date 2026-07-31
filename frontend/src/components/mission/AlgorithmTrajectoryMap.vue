<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Crosshair, Radio } from '@lucide/vue'
import type { AlgorithmRuntimeFrame } from '@/types/mission'

const props = defineProps<{ frame: AlgorithmRuntimeFrame | null; missionName: string; selectedDeviceCode?: string }>()
const emit = defineEmits<{ select: [code: string]; placeThreat: [x: number, y: number] }>()
const histories = reactive<Record<string, Array<{x:number;y:number}>>>({})
const displayFrame = ref<AlgorithmRuntimeFrame | null>(null)
const viewFrame = computed(() => displayFrame.value ?? props.frame)
const width=1100, height=520
// Keep one scene unit the same size on both axes. The previous 72×60 scene
// was stretched into a 670×444 rectangle, turning a circular USV enclosure
// into an ellipse and making 2-D motion disagree with Unity.
const sceneBounds={minX:-55,maxX:55,minY:-40,maxY:40}
// The responsive canvas is wider than the physical mission area. Expand only
// the visible X range so wide screens show more context without stretching
// distances or turning circular formations into ellipses.
const visibleXSpan=190.27
const visibleCenterX=()=>{
  const targets=viewFrame.value?.targets??[]
  return targets.find(item=>item.type==='CAPTURE_TARGET')?.x
    ??targets.find(item=>item.type==='ESCORT_TARGET')?.x
    ??0
}
const plot={x:22,y:52,w:1056,h:height-76}
const sx=(x:number)=>plot.x+(x-(visibleCenterX()-visibleXSpan/2))/visibleXSpan*plot.w
const sy=(y:number)=>plot.y+plot.h-(y-sceneBounds.minY)/(sceneBounds.maxY-sceneBounds.minY)*plot.h
const sceneScale=plot.w/visibleXSpan
const color=(type:string)=>type==='UAV'?'#ffc93e':type==='USV'?'#ff6464':type==='ESCORT_TARGET'?'#55e7a7':'#3cbff0'
let animationHandle: number | null = null
let activeAnimation = false
let activeRunId: number | null = null
const pendingFrames: AlgorithmRuntimeFrame[] = []

function copyFrame(frame: AlgorithmRuntimeFrame): AlgorithmRuntimeFrame {
  return {
    ...frame,
    agents: frame.agents.map(item => ({ ...item })),
    targets: frame.targets.map(item => ({ ...item })),
    metrics: { ...frame.metrics },
    route: frame.route.map(point => [...point]),
  }
}

function interpolateHeading(from: number, to: number, progress: number) {
  const delta = (to - from + 540) % 360 - 180
  return (from + delta * progress + 360) % 360
}

function animateToFrame(next: AlgorithmRuntimeFrame) {
  const from = displayFrame.value ? copyFrame(displayFrame.value) : null
  if (!from) {
    displayFrame.value = copyFrame(next)
    activeAnimation = false
    animateNextFrame()
    return
  }
  if (animationHandle !== null) window.cancelAnimationFrame(animationHandle)
  const startedAt = performance.now()
  const sourceDelta = Math.max(0, next.timestamp - from.timestamp)
  const duration = Math.min(110, Math.max(80, sourceDelta || 100))
  const fromAgents = new Map(from.agents.map(item => [item.code, item]))
  const fromTargets = new Map(from.targets.map(item => [item.code, item]))
  const step = (now: number) => {
    const linearProgress = Math.min(1, (now - startedAt) / duration)
    const progress = linearProgress
    const interpolate = <T extends {code:string;x:number;y:number;z:number;heading:number}>(item: T, previous?: T): T => previous ? ({
      ...item,
      x: previous.x + (item.x - previous.x) * progress,
      y: previous.y + (item.y - previous.y) * progress,
      z: previous.z + (item.z - previous.z) * progress,
      heading: interpolateHeading(previous.heading, item.heading, progress),
    }) : item
    displayFrame.value = {
      ...next,
      agents: next.agents.map(item => interpolate(item, fromAgents.get(item.code))),
      targets: next.targets.map(item => interpolate(item, fromTargets.get(item.code))),
    }
    if (linearProgress < 1) animationHandle = window.requestAnimationFrame(step)
    else {
      animationHandle = null
      activeAnimation = false
      animateNextFrame()
    }
  }
  animationHandle = window.requestAnimationFrame(step)
}

function animateNextFrame() {
  if (activeAnimation || pendingFrames.length === 0) return
  activeAnimation = true
  animateToFrame(pendingFrames.shift()!)
}

watch(()=>props.frame?.sequence,()=>{
  if(!props.frame)return
  if(activeRunId!==props.frame.runId){
    activeRunId=props.frame.runId
    Object.keys(histories).forEach(key=>delete histories[key])
    pendingFrames.splice(0,pendingFrames.length)
    displayFrame.value=null
  }
  for(const item of [...props.frame.agents,...props.frame.targets]){
    const history=histories[item.code]??(histories[item.code]=[])
    const previous=history[history.length-1]
    if(!previous||Math.hypot(previous.x-item.x,previous.y-item.y)>.08)history.push({x:item.x,y:item.y})
    if(history.length>500)history.splice(0,history.length-500)
  }
  pendingFrames.push(copyFrame(props.frame))
  // A browser tab may be throttled and receive a short backlog. Preserve the
  // newest two states instead of replaying stale frames for several seconds.
  if(pendingFrames.length>3)pendingFrames.splice(0,pendingFrames.length-2)
  animateNextFrame()
})

const routePath=computed(()=>viewFrame.value?.route?.map((point,index)=>`${index?'L':'M'} ${sx(point[0]??0)} ${sy(point[1]??0)}`).join(' ')||'')
const agentPath=(code:string)=>(histories[code]||[]).map((point,index)=>`${index?'L':'M'} ${sx(point.x)} ${sy(point.y)}`).join(' ')
const allObjects=computed(()=>viewFrame.value?[...viewFrame.value.agents,...viewFrame.value.targets]:[])
const uavs=computed(()=>viewFrame.value?.agents.filter(item=>item.type==='UAV')||[])
const usvs=computed(()=>viewFrame.value?.agents.filter(item=>item.type==='USV')||[])
const polygon=(items:Array<{x:number;y:number}>)=>items.map(item=>`${sx(item.x)},${sy(item.y)}`).join(' ')
const captureTarget=computed(()=>viewFrame.value?.targets.find(item=>item.type==='CAPTURE_TARGET'))
const displayLabel=(item:{code:string;type:string})=>{
  if(item.type==='ESCORT_TARGET')return '护航目标'
  if(item.type==='CAPTURE_TARGET')return '围捕目标'
  if(item.type==='THREAT_TARGET')return '威胁目标'
  return item.code.trim().toUpperCase().replace(/_/g,'-').replace(/^(UAV|USV)-(\d)$/,'$1-0$2')
}
type LabelLayout={x:number;y:number;width:number;height:number;leaderX:number;leaderY:number}
const labelLayouts=computed(()=>{
  const layouts:Record<string,LabelLayout>={}
  const occupied:Array<{left:number;right:number;top:number;bottom:number}>=[]
  const selected=props.selectedDeviceCode?.toLowerCase()
  const objects=[...allObjects.value].sort((left,right)=>{
    const priority=(item:{code:string;type:string})=>
      (item.code.toLowerCase()===selected?4:0)
      +(item.type.includes('TARGET')?2:0)
    return priority(right)-priority(left)
  })
  for(const item of objects){
    const markerX=sx(item.x),markerY=sy(item.y)
    const text=displayLabel(item)
    const labelWidth=Math.max(48,text.length*7+14)
    const labelHeight=20
    const candidates=[
      {x:markerX+12,y:markerY-28},
      {x:markerX-labelWidth-12,y:markerY-28},
      {x:markerX+12,y:markerY+10},
      {x:markerX-labelWidth-12,y:markerY+10},
      {x:markerX-labelWidth/2,y:markerY-38},
      {x:markerX-labelWidth/2,y:markerY+16},
    ]
    const within=(box:{left:number;right:number;top:number;bottom:number})=>
      box.left>=plot.x+2&&box.right<=plot.x+plot.w-2
      &&box.top>=plot.y+2&&box.bottom<=plot.y+plot.h-2
    const overlaps=(box:{left:number;right:number;top:number;bottom:number})=>
      occupied.some(other=>!(box.right+3<other.left||box.left-3>other.right||box.bottom+3<other.top||box.top-3>other.bottom))
    const chosen=candidates.find(candidate=>{
      const box={left:candidate.x,right:candidate.x+labelWidth,top:candidate.y,bottom:candidate.y+labelHeight}
      return within(box)&&!overlaps(box)
    })??candidates.find(candidate=>{
      const box={left:candidate.x,right:candidate.x+labelWidth,top:candidate.y,bottom:candidate.y+labelHeight}
      return within(box)
    })??{x:Math.min(plot.x+plot.w-labelWidth-2,Math.max(plot.x+2,markerX+10)),y:Math.min(plot.y+plot.h-labelHeight-2,Math.max(plot.y+2,markerY-26))}
    const box={left:chosen.x,right:chosen.x+labelWidth,top:chosen.y,bottom:chosen.y+labelHeight}
    occupied.push(box)
    layouts[item.code]={
      x:chosen.x,y:chosen.y,width:labelWidth,height:labelHeight,
      leaderX:Math.min(box.right,Math.max(box.left,markerX)),
      leaderY:Math.min(box.bottom,Math.max(box.top,markerY)),
    }
  }
  return layouts
})
const labelLayout=(code:string):LabelLayout=>labelLayouts.value[code]??{
  x:0,y:0,width:0,height:0,leaderX:0,leaderY:0,
}
const enclosureVisible=computed(()=>['ENCIRCLEMENT','CAPTURED'].includes(viewFrame.value?.phase||''))
const enclosureProgress=computed(()=>{
  if(viewFrame.value?.phase==='CAPTURED')return 1
  return Math.min(1,Math.max(.2,Number(viewFrame.value?.metrics.captureAgents||0)/6))
})
const usvRingRadius=computed(()=>{
  if(!captureTarget.value||!usvs.value.length)return 0
  return usvs.value.reduce((sum,item)=>sum+Math.hypot(item.x-captureTarget.value!.x,item.y-captureTarget.value!.y),0)/usvs.value.length*sceneScale
})
const phaseLabel=computed(()=>({
  ASSIGNMENT:'任务分配',TRANSIT:'航行接近',ENCIRCLEMENT:'形成围捕',CAPTURED:'围捕完成',
  ESCORTING:'正常护航',APPROACHING:'威胁接近',FORMING:'守卫编队形成',
  ORBITING:'持续动态盯防',THREAT_RESPONSE:'威胁响应',COMPLETED:'任务完成',
}[viewFrame.value?.phase||'']||viewFrame.value?.phase||'等待算法帧'))

function placeThreat(event:MouseEvent){
  if(props.frame?.algorithmCode!=='ESCORT_GUARD')return
  const svg=event.currentTarget as SVGSVGElement
  const matrix=svg.getScreenCTM()
  if(!matrix)return
  const pointer=svg.createSVGPoint()
  pointer.x=event.clientX
  pointer.y=event.clientY
  const local=pointer.matrixTransform(matrix.inverse())
  const px=local.x
  const py=local.y
  if(px<plot.x||px>plot.x+plot.w||py<plot.y||py>plot.y+plot.h)return
  const rawX=visibleCenterX()-visibleXSpan/2+(px-plot.x)/plot.w*visibleXSpan
  const rawY=sceneBounds.minY+(plot.y+plot.h-py)/plot.h*(sceneBounds.maxY-sceneBounds.minY)
  const x=Math.min(sceneBounds.maxX,Math.max(sceneBounds.minX,rawX))
  const y=Math.min(sceneBounds.maxY,Math.max(sceneBounds.minY,rawY))
  emit('placeThreat',x,y)
}

onBeforeUnmount(() => {
  if (animationHandle !== null) window.cancelAnimationFrame(animationHandle)
  pendingFrames.splice(0,pendingFrames.length)
})
</script>

<template>
  <section class="algorithm-map" :aria-label="missionName">
    <header>
      <span>ALGORITHM TRAJECTORY · SAME RUN</span>
      <div><b><Radio :size="14"/>{{ viewFrame?.algorithmCode||'WAITING' }}</b><em>{{ phaseLabel }}</em></div>
    </header>
    <div class="algorithm-map-body">
      <div class="algorithm-canvas">
        <svg :viewBox="`0 0 ${width} ${height}`" preserveAspectRatio="xMidYMid meet" @dblclick="placeThreat">
          <defs><pattern id="algorithm-grid" width="60" height="60" patternUnits="userSpaceOnUse"><path d="M60 0H0V60" fill="none" stroke="#2f8298" stroke-opacity=".18"/></pattern></defs>
          <rect :x="plot.x" :y="plot.y" :width="plot.w" :height="plot.h" class="water"/><rect :x="plot.x" :y="plot.y" :width="plot.w" :height="plot.h" fill="url(#algorithm-grid)"/>
          <path v-if="routePath" :d="routePath" class="route"/>
          <polygon
            v-if="viewFrame?.algorithmCode==='GB_SFLA_CS'&&uavs.length===3&&enclosureVisible"
            :points="polygon(uavs)"
            class="uav-formation"
            :style="{opacity:String(enclosureProgress)}"
          />
          <circle
            v-if="viewFrame?.algorithmCode==='GB_SFLA_CS'&&usvs.length===3&&captureTarget&&enclosureVisible"
            :cx="sx(captureTarget.x)"
            :cy="sy(captureTarget.y)"
            :r="usvRingRadius"
            class="usv-formation"
            :style="{opacity:String(enclosureProgress)}"
          />
          <path v-for="item in allObjects" :key="`${item.code}-trail`" :d="agentPath(item.code)" fill="none" :stroke="color(item.type)" class="trail"/>
          <g
            v-for="item in allObjects"
            :key="item.code"
            class="marker"
            :class="{selected:item.code.toLowerCase()===selectedDeviceCode?.toLowerCase()}"
            @click.stop="'role' in item&&emit('select',item.code.toLowerCase())"
          >
            <circle :cx="sx(item.x)" :cy="sy(item.y)" :r="item.type==='ESCORT_TARGET'?7:5" :fill="color(item.type)"/>
            <line
              :x1="sx(item.x)"
              :y1="sy(item.y)"
              :x2="sx(item.x)+Math.cos((item.heading||0)*Math.PI/180)*13"
              :y2="sy(item.y)-Math.sin((item.heading||0)*Math.PI/180)*13"
              :stroke="color(item.type)"
            />
            <line
              v-if="labelLayouts[item.code]"
              class="label-leader"
              :x1="sx(item.x)"
              :y1="sy(item.y)"
              :x2="labelLayout(item.code).leaderX"
              :y2="labelLayout(item.code).leaderY"
              :stroke="color(item.type)"
            />
            <rect
              v-if="labelLayouts[item.code]"
              class="label-box"
              :x="labelLayout(item.code).x"
              :y="labelLayout(item.code).y"
              :width="labelLayout(item.code).width"
              :height="labelLayout(item.code).height"
              :stroke="color(item.type)"
            />
            <text
              v-if="labelLayouts[item.code]"
              :x="labelLayout(item.code).x+labelLayout(item.code).width/2"
              :y="labelLayout(item.code).y+14"
              text-anchor="middle"
              :fill="color(item.type)"
            >{{ displayLabel(item) }}</text>
          </g>
          <text v-if="viewFrame?.algorithmCode==='ESCORT_GUARD'" :x="plot.x+10" :y="plot.y+plot.h-10" class="hint">双击水域可重新放置威胁目标</text>
          <text v-if="!viewFrame" :x="width/2" y="270" text-anchor="middle" class="waiting">等待真实算法轨迹帧</text>
        </svg>
      </div>
      <aside class="algorithm-metrics" aria-label="算法运行统计">
        <div class="metric-summary">
          <article><span>RUN</span><strong>{{ viewFrame?.runId||'--' }}</strong></article>
          <article><span>SEQ</span><strong>{{ viewFrame?.sequence||0 }}</strong></article>
          <article class="wide"><span>阶段</span><strong>{{ phaseLabel }}</strong></article>
          <article><span>UAV</span><strong>{{ uavs.length }}/3</strong></article>
          <article><span>USV</span><strong>{{ usvs.length }}/3</strong></article>
          <article><span>进度</span><strong>{{ Math.round(Number(viewFrame?.metrics.progress||0)*100) }}%</strong></article>
          <article><span>避障</span><strong>{{ viewFrame?.metrics.avoidanceCount||0 }}</strong></article>
        </div>
        <div class="coordinate-list">
          <div v-for="item in allObjects" :key="`${item.code}-legend`">
            <span :style="{color:color(item.type)}">{{ displayLabel(item) }}</span>
            <b>{{ item.x.toFixed(1) }}, {{ item.y.toFixed(1) }}</b>
          </div>
        </div>
      </aside>
    </div>
    <footer><span><Crosshair :size="14"/>2D / 3D 同源</span><b>{{ phaseLabel }}</b></footer>
  </section>
</template>

<style scoped>
.algorithm-map{height:100%;display:grid;grid-template-rows:auto minmax(0,1fr) auto;background:#03131b;color:#e6fbf8}
.algorithm-map header,.algorithm-map footer{display:flex;align-items:center;justify-content:space-between;padding:11px 14px;background:#061c25;border-bottom:1px solid #17414b}
.algorithm-map header span{color:#51d5e7;font-size:9px;font-weight:900;letter-spacing:.12em}
.algorithm-map header>div:last-child{display:flex;gap:8px}
.algorithm-map header b,.algorithm-map header em{display:flex;align-items:center;gap:5px;padding:5px 8px;font-size:9px;font-style:normal;border:1px solid #285661;border-radius:4px}
.algorithm-map header b{color:#55e7a7}
.algorithm-map-body{display:grid;grid-template-columns:minmax(0,1fr) clamp(220px,16vw,310px);min-height:0;background:#020b11}
.algorithm-canvas{position:relative;min-width:0;min-height:0;overflow:hidden;border-right:1px solid #173944}
.algorithm-canvas svg{position:absolute;inset:0;display:block;width:100%;height:100%;min-width:0;min-height:0;background:#020b11}
.water{fill:#041923;stroke:#2d6470}
.route{fill:none;stroke:#4ecfe4;stroke-width:2;stroke-dasharray:7 5}
.trail{stroke-width:1.6;stroke-opacity:.72}
.uav-formation{fill:#ffc93e;fill-opacity:.04;stroke:#ffc93e;stroke-width:1.5;stroke-dasharray:6 4}
.usv-formation{fill:#ff6464;fill-opacity:.03;stroke:#ff6464;stroke-width:1.5;stroke-dasharray:7 4}
.marker{cursor:pointer}
.marker text{font-size:9px;font-weight:700;paint-order:stroke;stroke:#020b11;stroke-width:2px}
.marker.selected circle{stroke:#fff;stroke-width:2}
.label-box{fill:#03131b;fill-opacity:.9;stroke-width:.8}
.label-leader{stroke-width:.8;stroke-opacity:.55}
.hint{fill:#64dce8;font-size:9px}
.waiting{fill:#688b91;font-size:13px}
.algorithm-metrics{display:flex;min-width:0;flex-direction:column;gap:14px;padding:clamp(14px,1.4vw,24px);overflow:auto;background:linear-gradient(180deg,#04151d,#020b11)}
.metric-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.metric-summary article{min-width:0;padding:10px;border:1px solid rgba(76,180,202,.18);border-radius:6px;background:rgba(8,35,45,.68)}
.metric-summary article.wide{grid-column:1/-1}
.metric-summary span,.metric-summary strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.metric-summary span{color:#688f94;font-size:9px;letter-spacing:.08em}
.metric-summary strong{margin-top:5px;color:#dff7f5;font-size:13px}
.coordinate-list{display:grid;gap:3px}
.coordinate-list div{display:flex;align-items:center;justify-content:space-between;gap:10px;min-width:0;padding:7px 2px;border-bottom:1px solid rgba(76,180,202,.1);font-size:10px}
.coordinate-list span{font-weight:800}
.coordinate-list b{color:#a9c6c9;font-weight:600;white-space:nowrap}
.algorithm-map footer{border-top:1px solid #17414b;border-bottom:0;color:#7fa3a7;font-size:10px}
.algorithm-map footer span{display:flex;align-items:center;gap:5px}
.algorithm-map footer b{margin-left:auto;color:#55e7a7}
.algorithm-map header svg,.algorithm-map footer svg{width:auto;height:auto;min-height:0;background:none}

@media (max-width: 920px) {
  .algorithm-map-body{grid-template-columns:1fr;overflow:auto}
  .algorithm-canvas{min-height:460px;border-right:0;border-bottom:1px solid #173944}
  .algorithm-metrics{overflow:visible}
  .metric-summary{grid-template-columns:repeat(4,minmax(0,1fr))}
  .metric-summary article.wide{grid-column:span 2}
  .coordinate-list{grid-template-columns:repeat(2,minmax(0,1fr))}
}

@media (min-width: 1920px) {
  .algorithm-map header,.algorithm-map footer{padding:12px 18px}
  .algorithm-map header span{font-size:10px}
  .algorithm-map header b,.algorithm-map header em{padding:6px 10px;font-size:10px}
  .algorithm-metrics{padding:22px}
  .metric-summary article{padding:12px}
  .metric-summary strong{font-size:15px}
  .coordinate-list div{padding-block:9px;font-size:11px}
}
</style>
