<script setup lang="ts">
import { Camera, Radio, Zap } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import ConsoleLayout from '@/components/layout/ConsoleLayout.vue'
import { useRadarSensorStore } from '@/stores/radarSensor'
import { useUnityBridgeStore } from '@/stores/unityBridge'
import { useVisualSensorStore } from '@/stores/visualSensor'

const store=useVisualSensorStore(),radarStore=useRadarSensorStore(),bridge=useUnityBridgeStore()
const quality=ref<'720p'|'1080p'>('1080p'),targetFps=30
let timer:number|undefined
const overview=computed(()=>store.displayOverview)
const sensors=computed(()=>overview.value.sensors)
const frames=computed(()=>store.channels.SYSTEM_OVERVIEW.frameUrls)
const stats=computed(()=>store.streamStats)
const focused=computed(()=>sensors.value.find(item=>item.cameraId===overview.value.focusedCameraId)||sensors.value[0])
const orbit=computed(()=>sensors.value.filter(item=>item.cameraId!==focused.value?.cameraId).slice(0,5))
const detection=computed(()=>radarStore.overview?.latestTargetId?{id:radarStore.overview.latestTargetId,count:radarStore.overview.detectionCount}:null)
const online=computed(()=>store.unityBridgeReady||overview.value.gatewayConnected)
const channelLabel=(sensor:{deviceType:string;cameraId:string})=>`${sensor.deviceType==='UAV'?'空中视角':'水面视角'} ${sensor.cameraId.slice(-2)}`
function subscribe(cameraId=focused.value?.cameraId||'uav_01'){
  bridge.sendFor('SYSTEM_OVERVIEW','visualSensorSubscribe',{enabled:true,focusedCameraId:cameraId,displayMode:'focus',quality:quality.value,targetFps,gpuDirect:true,jpegFallback:false,thumbnailFps:4,focusedFps:targetFps})
}
async function select(cameraId:string){
  await store.select(cameraId)
  subscribe(cameraId)
  await store.refreshFrames(true)
}
onMounted(async()=>{
  await Promise.all([store.refreshOverview(),radarStore.refresh(true)])
  const cameraId=overview.value.focusedCameraId||focused.value?.cameraId||'uav_01'
  await store.select(cameraId)
  subscribe(cameraId)
  await store.refreshFrames()
  timer=window.setInterval(()=>{void store.refreshOverview();void store.refreshFrames();void radarStore.refresh(true)},2500)
})
onBeforeUnmount(()=>{bridge.sendFor('SYSTEM_OVERVIEW','visualSensorSubscribe',{enabled:false,focusedCameraId:focused.value?.cameraId||'uav_01',displayMode:'off',quality:quality.value,targetFps,gpuDirect:true,jpegFallback:false});if(timer)clearInterval(timer);store.disposeFrames()})
</script>

<template>
  <ConsoleLayout title="光电视觉" eyebrow="ELECTRO-OPTICAL VISION">
    <template #actions><span class="top-chip" :class="{online}"><Zap :size="14"/>{{ online?'Unity 视觉链路在线':'等待视觉链路' }}</span><span class="top-chip"><Camera :size="14"/>{{ overview.onlineCount }}/{{ overview.totalCount }} 路在线</span></template>
    <section class="optical-stage">
      <header class="stage-title"><span>LIVE OPTICAL NETWORK</span><b>六路协同视觉回传</b><small>中心通道为当前关注视角，点击外围通道即可切换</small></header>
      <div class="quality"><button :class="{active:quality==='720p'}" @click="quality='720p';subscribe()">720P</button><button :class="{active:quality==='1080p'}" @click="quality='1080p';subscribe()">1080P</button></div>
      <svg class="links" viewBox="0 0 1200 720" preserveAspectRatio="none"><path d="M600 360L205 160M600 360L600 105M600 360L995 160M600 360L265 610M600 360L935 610"/></svg>
      <div class="health-arc"><span v-for="sensor in sensors" :key="sensor.cameraId" :class="{online:sensor.status==='ONLINE'}"><i/>{{ channelLabel(sensor) }}</span></div>
      <div class="feed-field">
        <button v-for="(sensor,index) in orbit" :key="sensor.cameraId" class="feed satellite" :class="`p${index+1}`" @click="select(sensor.cameraId)">
          <img v-if="frames[sensor.cameraId]" :src="frames[sensor.cameraId]" alt=""/><div v-else class="empty"><Radio :size="20"/><span>等待该通道帧</span></div>
          <span class="feed-label">{{ channelLabel(sensor) }}<i :class="{online:sensor.status==='ONLINE'}"/></span>
        </button>
        <button v-if="focused" class="feed focus" @click="select(focused.cameraId)">
          <div class="unity-runtime" data-unity-runtime-viewport="visual-sensors-live"></div>
          <img v-if="frames[focused.cameraId]" :src="frames[focused.cameraId]" alt="当前视觉通道"/>
          <div v-else class="empty focus-empty"><Radio :size="28"/><strong>{{ online?'正在等待当前设备视觉帧':'正在连接 Unity 视觉' }}</strong><span>当前通道 {{ channelLabel(focused) }}</span></div>
          <span class="feed-label">{{ channelLabel(focused) }}<i :class="{online:focused.status==='ONLINE'}"/></span>
          <aside v-if="detection" class="detection"><span>TARGET DETECTED</span><b>{{ detection.id }}</b><small>真实检测事件 · 累计 {{ detection.count }}</small></aside>
        </button>
      </div>
      <article class="latency"><span>实时帧率</span><b>{{ stats?.measuredFps?.toFixed(1)||'--' }} FPS</b><i/><span>渲染耗时</span><b>{{ stats?.renderMs?.toFixed(1)||'--' }} ms</b></article>
      <article class="source"><span>当前链路</span><b>{{ overview.gatewayDetail }}</b><small>{{ stats?.streamWidth||'--' }} × {{ stats?.streamHeight||'--' }} · GPU Direct</small></article>
    </section>
  </ConsoleLayout>
</template>

<style scoped>
.top-chip{display:flex;align-items:center;gap:6px;padding:8px 10px;border:1px solid #24505a;border-radius:6px;color:#82a6aa;font-size:11px}.top-chip.online{color:#55e5b2}.optical-stage{position:relative;height:calc(100vh - 132px);min-height:690px;overflow:hidden;border:1px solid #17424d;border-radius:12px;background:radial-gradient(circle at 50% 48%,#0a2b36 0,#041821 43%,#020d13 77%);box-shadow:inset 0 0 90px #0008}.stage-title{position:absolute;z-index:6;left:22px;top:20px;display:grid;gap:3px}.stage-title span{color:#51d7e8;font-size:9px;letter-spacing:.17em}.stage-title b{font-size:18px}.stage-title small{color:#70969b}.quality{position:absolute;z-index:8;right:20px;top:20px;display:flex;padding:3px;border:1px solid #24505a;border-radius:7px;background:#04151c}.quality button{padding:7px 13px;border:0;border-radius:5px;background:transparent;color:#73989d}.quality button.active{background:#61dccf;color:#001216;font-weight:800}.links{position:absolute;inset:8% 4% 4%;width:92%;height:88%;pointer-events:none}.links path{fill:none;stroke:#42bcd0;stroke-width:1;stroke-dasharray:6 8;opacity:.32}.health-arc{position:absolute;z-index:6;left:50%;top:9%;display:flex;width:min(68%,850px);justify-content:space-between;transform:translateX(-50%)}.health-arc:before{position:absolute;z-index:-1;top:9px;left:3%;width:94%;height:70px;border-top:1px solid #275e69;border-radius:50%;content:''}.health-arc span{display:grid;justify-items:center;gap:5px;color:#668c91;font-size:9px}.health-arc i{width:7px;height:7px;border:1px solid #51777c;border-radius:50%;background:#07171d}.health-arc span.online{color:#b9e5e2}.health-arc span.online i{border-color:#53e6b0;background:#53e6b0;box-shadow:0 0 8px #53e6b0}.feed{position:absolute;z-index:4;overflow:hidden;padding:0;border:1px solid #286270;border-radius:9px;background:#061821;box-shadow:0 16px 35px #0008;cursor:pointer}.feed img,.unity-runtime{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.focus{left:50%;top:50%;width:42%;aspect-ratio:16/9;transform:translate(-50%,-48%);border-color:#58ddd1;box-shadow:0 20px 55px #000b,0 0 0 1px #58ddd133}.satellite{width:22%;aspect-ratio:16/9}.p1{left:3%;top:18%}.p2{left:39%;top:13%}.p3{right:3%;top:18%}.p4{left:10%;bottom:8%}.p5{right:10%;bottom:8%}.feed-label{position:absolute;z-index:3;left:9px;top:8px;display:flex;align-items:center;gap:7px;padding:5px 8px;border:1px solid #2a5963;border-radius:5px;background:#03151dcc;color:#e5f7f5;font-size:10px}.feed-label i{width:6px;height:6px;border-radius:50%;background:#5b7377}.feed-label i.online{background:#52e5ae;box-shadow:0 0 7px #52e5ae}.empty{position:absolute;inset:0;display:grid;place-content:center;justify-items:center;gap:7px;color:#668c91;background:linear-gradient(145deg,#092630,#041820)}.detection{position:absolute;z-index:5;right:5%;bottom:12%;display:grid;gap:4px;padding:10px 14px;border:1px solid #ffbe42;border-radius:6px;background:#241b09e8;text-align:left}.detection span{color:#ffc64e;font-size:8px;letter-spacing:.12em}.detection b{color:#fff}.detection small{color:#c8aa6b}.latency,.source{position:absolute;z-index:6;display:grid;gap:4px;padding:10px 12px;border:1px solid #24505a;border-radius:7px;background:#041820dc;backdrop-filter:blur(6px)}.latency{left:2%;bottom:2%;grid-template-columns:auto auto}.latency span,.source span{color:#70979c;font-size:9px}.latency b,.source b{font-size:11px}.source{right:2%;bottom:2%;max-width:260px}.source small{color:#5d8287;font-size:9px}@media(max-width:1450px){.optical-stage{min-height:630px}.satellite{width:20%}.focus{width:43%}.p2{left:40%}.health-arc{top:10%}}@media(max-width:1050px){.optical-stage{height:780px}.focus{width:58%}.satellite{width:27%}.p1{top:20%}.p2{display:none}.p3{top:20%}.p4{bottom:9%}.p5{bottom:9%}.health-arc{width:80%}}
.optical-stage{height:calc(100dvh - 174px);min-height:610px}
@media(max-height:760px){.optical-stage{min-height:560px}.satellite{width:19%}.focus{width:39%}}
.feed-field{position:absolute;z-index:4;inset:112px 34px 56px;display:grid;grid-template-columns:repeat(12,minmax(0,1fr));grid-template-rows:repeat(10,minmax(0,1fr));gap:12px 14px;min-width:0;min-height:0}
.feed-field .feed{position:relative;inset:auto;width:auto;height:auto;min-width:0;min-height:0;transform:none;aspect-ratio:auto;place-self:stretch}
.feed-field .focus{grid-column:4/10;grid-row:3/9;z-index:5}
.feed-field .p1{grid-column:1/4;grid-row:2/5}
.feed-field .p2{grid-column:6/8;grid-row:1/3}
.feed-field .p3{grid-column:10/13;grid-row:2/5}
.feed-field .p4{grid-column:1/4;grid-row:6/9}
.feed-field .p5{grid-column:10/13;grid-row:6/9}
.feed-field .feed img{z-index:2}
.feed-field .unity-runtime{z-index:0;opacity:0;pointer-events:none}
.feed-field .empty{z-index:2}
.focus-empty span{font-size:10px;color:#6c969a}
@media(max-width:1450px){.feed-field{inset:104px 24px 52px;gap:10px 12px}.feed-field .satellite{width:auto}.feed-field .focus{width:auto}.feed-field .p2{grid-column:6/8}}
@media(max-width:1050px){.feed-field{inset:108px 18px 54px;grid-template-columns:repeat(10,minmax(0,1fr));grid-template-rows:repeat(12,minmax(0,1fr))}.feed-field .focus{grid-column:3/9;grid-row:4/10}.feed-field .p1{grid-column:1/4;grid-row:1/4}.feed-field .p2{display:block;grid-column:4/8;grid-row:1/4}.feed-field .p3{grid-column:8/11;grid-row:1/4}.feed-field .p4{grid-column:1/5;grid-row:10/13}.feed-field .p5{grid-column:7/11;grid-row:10/13}}
</style>
