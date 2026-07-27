<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Crosshair, Radio } from '@lucide/vue'
import type { AlgorithmRuntimeFrame } from '@/types/mission'

const props = defineProps<{ frame: AlgorithmRuntimeFrame | null; missionName: string; selectedDeviceCode?: string }>()
const emit = defineEmits<{ select: [code: string]; placeThreat: [x: number, y: number] }>()
const histories = reactive<Record<string, Array<{x:number;y:number}>>>({})
const displayFrame = ref<AlgorithmRuntimeFrame | null>(null)
const viewFrame = computed(() => displayFrame.value ?? props.frame)
const width=900, height=520, side=190
const plot={x:20,y:52,w:width-side-40,h:height-76}
const bounds={minX:-36,maxX:36,minY:-30,maxY:30}
const sx=(x:number)=>plot.x+(x-bounds.minX)/(bounds.maxX-bounds.minX)*plot.w
const sy=(y:number)=>plot.y+plot.h-(y-bounds.minY)/(bounds.maxY-bounds.minY)*plot.h
const color=(type:string)=>type==='UAV'?'#ffc93e':type==='USV'?'#ff6464':type==='ESCORT_TARGET'?'#55e7a7':'#3cbff0'
let animationHandle: number | null = null

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
    return
  }
  if (animationHandle !== null) window.cancelAnimationFrame(animationHandle)
  const startedAt = performance.now()
  const sourceDelta = Math.max(0, next.timestamp - from.timestamp)
  const duration = Math.min(160, Math.max(90, sourceDelta || 100))
  const fromAgents = new Map(from.agents.map(item => [item.code, item]))
  const fromTargets = new Map(from.targets.map(item => [item.code, item]))
  const step = (now: number) => {
    const progress = Math.min(1, (now - startedAt) / duration)
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
    if (progress < 1) animationHandle = window.requestAnimationFrame(step)
    else animationHandle = null
  }
  animationHandle = window.requestAnimationFrame(step)
}

watch(()=>props.frame?.sequence,()=>{
  if(!props.frame)return
  for(const item of [...props.frame.agents,...props.frame.targets]){
    const history=histories[item.code]??(histories[item.code]=[])
    const previous=history[history.length-1]
    if(!previous||Math.hypot(previous.x-item.x,previous.y-item.y)>.08)history.push({x:item.x,y:item.y})
    if(history.length>500)history.splice(0,history.length-500)
  }
  animateToFrame(props.frame)
})

const routePath=computed(()=>viewFrame.value?.route?.map((point,index)=>`${index?'L':'M'} ${sx(point[0]??0)} ${sy(point[1]??0)}`).join(' ')||'')
const agentPath=(code:string)=>(histories[code]||[]).map((point,index)=>`${index?'L':'M'} ${sx(point.x)} ${sy(point.y)}`).join(' ')
const allObjects=computed(()=>viewFrame.value?[...viewFrame.value.agents,...viewFrame.value.targets]:[])
const uavs=computed(()=>viewFrame.value?.agents.filter(item=>item.type==='UAV')||[])
const usvs=computed(()=>viewFrame.value?.agents.filter(item=>item.type==='USV')||[])
const polygon=(items:Array<{x:number;y:number}>)=>items.map(item=>`${sx(item.x)},${sy(item.y)}`).join(' ')
const phaseLabel=computed(()=>({ASSIGNMENT:'任务分配',TRANSIT:'航行接近',ENCIRCLEMENT:'形成围捕',CAPTURED:'围捕完成',ESCORTING:'正常护航',THREAT_RESPONSE:'威胁响应',COMPLETED:'任务完成'}[viewFrame.value?.phase||'']||viewFrame.value?.phase||'等待算法帧'))

function placeThreat(event:MouseEvent){
  if(props.frame?.algorithmCode!=='ESCORT_GUARD')return
  const svg=event.currentTarget as SVGElement;const rect=svg.getBoundingClientRect();const px=(event.clientX-rect.left)/rect.width*width;const py=(event.clientY-rect.top)/rect.height*height
  if(px<plot.x||px>plot.x+plot.w||py<plot.y||py>plot.y+plot.h)return
  const x=bounds.minX+(px-plot.x)/plot.w*(bounds.maxX-bounds.minX);const y=bounds.minY+(plot.y+plot.h-py)/plot.h*(bounds.maxY-bounds.minY)
  emit('placeThreat',x,y)
}

onBeforeUnmount(() => {
  if (animationHandle !== null) window.cancelAnimationFrame(animationHandle)
})
</script>

<template>
  <section class="algorithm-map">
    <header><div><span>ALGORITHM TRAJECTORY · SAME RUN</span><h3>{{ missionName }}</h3></div><div><b><Radio :size="14"/>{{ viewFrame?.algorithmCode||'WAITING' }}</b><em>{{ phaseLabel }}</em></div></header>
    <svg :viewBox="`0 0 ${width} ${height}`" @dblclick="placeThreat">
      <defs><pattern id="algorithm-grid" width="60" height="60" patternUnits="userSpaceOnUse"><path d="M60 0H0V60" fill="none" stroke="#2f8298" stroke-opacity=".18"/></pattern></defs>
      <rect :x="plot.x" :y="plot.y" :width="plot.w" :height="plot.h" class="water"/><rect :x="plot.x" :y="plot.y" :width="plot.w" :height="plot.h" fill="url(#algorithm-grid)"/>
      <path v-if="routePath" :d="routePath" class="route"/>
      <polygon v-if="viewFrame?.algorithmCode==='GB_SFLA_CS'&&uavs.length===3" :points="polygon(uavs)" class="uav-formation"/>
      <polygon v-if="viewFrame?.algorithmCode==='GB_SFLA_CS'&&usvs.length===3" :points="polygon(usvs)" class="usv-formation"/>
      <path v-for="item in allObjects" :key="`${item.code}-trail`" :d="agentPath(item.code)" fill="none" :stroke="color(item.type)" class="trail"/>
      <g v-for="item in allObjects" :key="item.code" class="marker" :class="{selected:item.code.toLowerCase()===selectedDeviceCode?.toLowerCase()}" @click.stop="'role' in item&&emit('select',item.code.toLowerCase())"><circle :cx="sx(item.x)" :cy="sy(item.y)" :r="item.type==='ESCORT_TARGET'?8:6" :fill="color(item.type)"/><line :x1="sx(item.x)" :y1="sy(item.y)" :x2="sx(item.x)+Math.cos((item.heading||0)*Math.PI/180)*13" :y2="sy(item.y)-Math.sin((item.heading||0)*Math.PI/180)*13" :stroke="color(item.type)"/><text :x="sx(item.x)+8" :y="sy(item.y)-8" :fill="color(item.type)">{{ item.code }}</text></g>
      <g class="statistics"><text x="730" y="76">RUN {{ viewFrame?.runId||'--' }}</text><text x="730" y="98">SEQ {{ viewFrame?.sequence||0 }}</text><text x="730" y="120">PHASE {{ phaseLabel }}</text><text x="730" y="153">UAV {{ uavs.length }}/3</text><text x="730" y="174">USV {{ usvs.length }}/3</text><text x="730" y="207">PROGRESS {{ Math.round(Number(viewFrame?.metrics.progress||0)*100) }}%</text><text x="730" y="228">AVOID {{ viewFrame?.metrics.avoidanceCount||0 }}</text><text v-for="(item,index) in allObjects" :key="`${item.code}-legend`" x="730" :y="266+index*21" :fill="color(item.type)">{{ item.code }} {{ item.x.toFixed(1) }}, {{ item.y.toFixed(1) }}</text></g>
      <text v-if="viewFrame?.algorithmCode==='ESCORT_GUARD'" :x="plot.x+10" :y="plot.y+plot.h-10" class="hint">双击水域可重新放置威胁目标</text>
      <text v-if="!viewFrame" x="330" y="270" class="waiting">等待真实算法轨迹帧</text>
    </svg>
    <footer><span><Crosshair :size="14"/>2D / 3D 同源</span><b>{{ phaseLabel }}</b></footer>
  </section>
</template>

<style scoped>
.algorithm-map{height:100%;display:grid;grid-template-rows:auto minmax(0,1fr) auto;background:#03131b;color:#e6fbf8}.algorithm-map header,.algorithm-map footer{display:flex;align-items:center;justify-content:space-between;padding:11px 14px;background:#061c25;border-bottom:1px solid #17414b}.algorithm-map header span{color:#51d5e7;font-size:9px;font-weight:900;letter-spacing:.12em}.algorithm-map h3{margin:4px 0 0;font-size:15px}.algorithm-map header>div:last-child{display:flex;gap:8px}.algorithm-map header b,.algorithm-map header em{display:flex;align-items:center;gap:5px;padding:5px 8px;font-size:9px;font-style:normal;border:1px solid #285661;border-radius:4px}.algorithm-map header b{color:#55e7a7}.algorithm-map svg{display:block;width:100%;height:100%;min-height:460px;background:#020b11}.water{fill:#041923;stroke:#2d6470}.route{fill:none;stroke:#4ecfe4;stroke-width:2;stroke-dasharray:7 5}.trail{stroke-width:1.6;stroke-opacity:.72}.uav-formation{fill:#ffc93e;fill-opacity:.04;stroke:#ffc93e;stroke-width:1.5;stroke-dasharray:6 4}.usv-formation{fill:#ff6464;fill-opacity:.03;stroke:#ff6464;stroke-width:1.5;stroke-dasharray:7 4}.marker{cursor:pointer}.marker text{font-size:9px;paint-order:stroke;stroke:#020b11;stroke-width:2px}.marker.selected circle{stroke:#fff;stroke-width:2}.statistics text{fill:#bad7dc;font:10px Arial}.hint{fill:#64dce8;font-size:9px}.waiting{fill:#688b91;font-size:13px}.algorithm-map footer{border-top:1px solid #17414b;border-bottom:0;color:#7fa3a7;font-size:10px}.algorithm-map footer span{display:flex;align-items:center;gap:5px}.algorithm-map footer b{margin-left:auto;color:#55e7a7}
.algorithm-map header svg,.algorithm-map footer svg{width:auto;height:auto;min-height:0;background:none}
</style>
