<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import {
  AlertTriangle,
  Beaker,
  Bot,
  CircleCheck,
  Clock3,
  Cpu,
  FlaskConical,
  Plus,
  Radio,
  Search,
  Settings2,
  Waves,
} from '@lucide/vue'

import ConsoleLayout from '@/components/layout/ConsoleLayout.vue'
import MissionListPanel from '@/components/mission/MissionListPanel.vue'
import AlgorithmMissionControlPanel from '@/components/mission/AlgorithmMissionControlPanel.vue'
import AlgorithmMissionStatusPanel from '@/components/mission/AlgorithmMissionStatusPanel.vue'
import AlgorithmTacticalMap from '@/components/mission/AlgorithmTacticalMap.vue'
import MissionConfigDialog from '@/components/mission/MissionConfigDialog.vue'
import MissionStartCheckDialog from '@/components/mission/MissionStartCheckDialog.vue'
import MissionEventDrawer from '@/components/mission/MissionEventDrawer.vue'
import { createMission, deleteMission, executeMissionAction, fetchMission, fetchMissionPreflight, fetchMissionSummary, updateMission } from '@/api/mission'
import type { MissionAction } from '@/api/mission'
import type { AlgorithmRunStatus, AlgorithmType } from '@/api/algorithm'
import { useAlgorithmStore } from '@/stores/algorithm'
import { useDeviceStore } from '@/stores/device'
import { useMissionStore } from '@/stores/mission'
import { useMonitoringStore } from '@/stores/monitoring'
import { usePerceptionStore } from '@/stores/perception'
import { useTrajectoryStore } from '@/stores/trajectory'
import { useUnityBridgeStore } from '@/stores/unityBridge'
import { useMissionTrajectorySessionStore } from '@/stores/missionTrajectorySession'
import { useUnityViewportStore } from '@/stores/unityViewport'
import type { Mission, MissionDetail, MissionExecutionMode, MissionPreflight, MissionSavePayload, MissionStatus, MissionSummary, MissionType } from '@/types/mission'

const missionStore=useMissionStore()
const algorithmStore=useAlgorithmStore()
const perceptionStore=usePerceptionStore()
const deviceStore=useDeviceStore()
const monitoringStore=useMonitoringStore()
const trajectoryStore=useTrajectoryStore()
const unityBridgeStore=useUnityBridgeStore()
const sessionStore=useMissionTrajectorySessionStore()
const unityViewportStore=useUnityViewportStore()
const router=useRouter()

const summary=ref<MissionSummary>({total:0,ready:0,running:0,abnormal:0})
const selectedMission=ref<Mission|null>(null)
const detail=ref<MissionDetail|null>(null)
const configVisible=ref(false)
const configReadonly=ref(false)
const startVisible=ref(false)
const preflight=ref<MissionPreflight|null>(null)
const preflightLoading=ref(false)
const eventVisible=ref(false)
const saving=ref(false)
const actionBusy=ref(false)
const keyword=ref('')
const typeFilter=ref<MissionType|undefined>()
const statusFilter=ref<MissionStatus|undefined>()
const modeFilter=ref<MissionExecutionMode|undefined>()

const missionUnityChannel=computed(()=>unityBridgeStore.channels.MISSION_CENTER)
const missionTrajectoryFrame=computed(()=>trajectoryStore.channels.MISSION_CENTER.frame)
const trajectoryLive=computed(()=>missionUnityChannel.value.connected&&!!missionTrajectoryFrame.value&&Date.now()-missionTrajectoryFrame.value.receivedAt<3000)
const recentRuns=computed(()=>missionStore.records.filter(mission=>['RUNNING','PAUSED','COMPLETED','FAILED','CANCELLED'].includes(mission.status)).slice(0,4))
const missionAlgorithmRun=computed(()=>algorithmStore.activeRun??algorithmStore.latestRun)

async function load(page=missionStore.page){
  await Promise.all([
    missionStore.refresh({page,size:8,keyword:keyword.value||undefined,type:typeFilter.value,status:statusFilter.value,executionMode:modeFilter.value}),
    fetchMissionSummary().then(value=>summary.value=value),
    monitoringStore.refresh({},true),
  ])
}
async function loadDetail(mission:Mission){
  selectedMission.value=mission
  detail.value=await fetchMission(mission.id)
  sessionStore.bind(detail.value.mission.id,detail.value.currentRun?.id||null)
  return detail.value
}
async function openConfig(mission?:Mission,readonly=false){configReadonly.value=readonly;detail.value=mission?await loadDetail(mission):null;selectedMission.value=mission||null;configVisible.value=true}
async function save(payload:MissionSavePayload){saving.value=true;try{if(selectedMission.value)await updateMission(selectedMission.value.id,payload);else await createMission(payload);ElMessage.success('任务配置已保存');configVisible.value=false;await load(0)}catch(error){ElMessage.error(error instanceof Error?error.message:'保存失败')}finally{saving.value=false}}
async function waitForMissionUnity(timeoutMs=30000){
  const started=Date.now()
  while(Date.now()-started<timeoutMs){
    const agents=missionTrajectoryFrame.value?.agents.filter(agent=>agent.type==='UAV'||agent.type==='USV')??[]
    const uavCount=agents.filter(agent=>agent.type==='UAV').length
    const usvCount=agents.filter(agent=>agent.type==='USV').length
    if(missionUnityChannel.value.connected&&missionUnityChannel.value.controlsReady&&uavCount>=3&&usvCount>=3)return
    await new Promise(resolve=>window.setTimeout(resolve,250))
  }
  throw new Error('任务中心 Unity 尚未完成指令桥和三机三艇轨迹初始化，请稍后重试')
}
async function openStart(mission:Mission){
  await loadDetail(mission)
  unityViewportStore.createMissionInstance(mission.id)
  await nextTick()
  preflightLoading.value=true
  startVisible.value=true
  try{
    await waitForMissionUnity()
    preflight.value=await fetchMissionPreflight(mission.id,unityViewportStore.missionInstanceId)
  }catch(error){
    ElMessage.error(error instanceof Error?error.message:'启动检查失败')
    startVisible.value=false
  }finally{preflightLoading.value=false}
}

function missionUnityCommand(action:MissionAction){return {start:'missionStart',pause:'missionPause',resume:'missionResume',complete:'missionComplete',fail:'missionFail',cancel:'missionCancel',ready:'missionResume'}[action]}

function algorithmStatusLabel(status?:AlgorithmRunStatus){
  return status ? ({PENDING:'等待算法 ACK',RUNNING:'算法运行中',COMPLETED:'算法完成',FAILED:'算法异常',TIMEOUT:'算法超时',STOPPED:'算法已停止'} as Partial<Record<AlgorithmRunStatus,string>>)[status] ?? status : '未启动'
}
function resolveMissionAlgorithmType(mission:Mission):AlgorithmType{
  const text=`${mission.name} ${mission.targetName??''} ${mission.targetBehavior??''}`
  return text.includes('护航')||text.toUpperCase().includes('ESCORT')?'ESCORT_DEFENSE':'CAPTURE'
}
function missionAlgorithmPayload(){
  const mission=detail.value?.mission
  const devices=detail.value?.devices??[]
  const uavIds=devices.filter(device=>device.type==='UAV'&&device.code).map(device=>device.code!.toLowerCase().replace(/-/g,'_'))
  const usvIds=devices.filter(device=>device.type==='USV'&&device.code).map(device=>device.code!.toLowerCase().replace(/-/g,'_'))
  return {
    algorithmType: mission ? resolveMissionAlgorithmType(mission) : 'CAPTURE' as AlgorithmType,
    targetId: perceptionStore.targets[0]?.targetId??'target_01',
    uavIds: uavIds.length?uavIds:['uav_01','uav_02','uav_03'],
    usvIds: usvIds.length?usvIds:['usv_01','usv_02','usv_03'],
    parameters:{source:'mission-control',missionId:mission?.id,missionName:mission?.name,runId:detail.value?.currentRun?.id,runtimeInstanceId:unityViewportStore.missionInstanceId},
  }
}
async function startMissionAlgorithm(){
  const payload=missionAlgorithmPayload()
  const run=await algorithmStore.start(payload)
  unityBridgeStore.sendFor('MISSION_CENTER','algorithmStart',{commandId:run.commandId,algorithmType:run.algorithmType,targetId:run.targetId,uavIds:payload.uavIds,usvIds:payload.usvIds,missionId:detail.value?.mission.id,runId:detail.value?.currentRun?.id})
  unityBridgeStore.sendFor('MISSION_CENTER','perceptionTargets',{targets:perceptionStore.targets})
  ElMessage.warning(`${run.algorithmType==='CAPTURE'?'围捕':'护航防守'}算法指令已生成：${run.commandId}，等待算法组 ACK`)
}
async function stopMissionAlgorithm(reason:string){
  const active=algorithmStore.activeRun
  if(!active)return
  await algorithmStore.stop({commandId:active.commandId,reason}).catch(()=>[])
  unityBridgeStore.sendFor('MISSION_CENTER','algorithmStop',{commandId:active.commandId,reason})
}

async function runMissionAction(action:MissionAction){
  if(!detail.value)return
  if(action==='cancel'){
    try{
      await ElMessageBox.confirm(
        '终止后将停止当前任务中心 RUN，并向任务中心 Unity 下发 missionCancel。系统总览不会受到影响。',
        '确认终止任务',
        {type:'warning',confirmButtonText:'确认终止',cancelButtonText:'取消',customClass:'mission-confirm-message-box'},
      )
    }catch{return false}
  }
  actionBusy.value=true
  try{
    if(action!=='ready'&&!missionUnityChannel.value.connected)throw new Error('任务中心 Unity WebGL 尚未连接，未创建控制指令')
    const result=await executeMissionAction(detail.value.mission.id,action,'MISSION_CONTROL',unityViewportStore.missionInstanceId)
    detail.value=result.detail
    if(result.command){
      if(['FAILED','TIMEOUT'].includes(result.command.status))throw new Error(result.command.detail||'指令下发失败')
      const ack=await unityBridgeStore.sendControlCommandAndWaitFor('MISSION_CENTER',missionUnityCommand(action),'',result.command.commandKey)
      if(!ack.success)throw new Error(ack.status||'Unity 未确认任务指令')
      detail.value=await fetchMission(detail.value.mission.id)
    }
    selectedMission.value=detail.value.mission
    sessionStore.bind(detail.value.mission.id,detail.value.currentRun?.id||null)
    if(action==='start'){
      sessionStore.start(missionTrajectoryFrame.value?.sequence||0,detail.value.currentRun?.id)
      await startMissionAlgorithm()
    }
    if(action==='pause'){
      sessionStore.pause()
      await stopMissionAlgorithm('任务中心暂停任务')
    }
    if(action==='resume'){
      sessionStore.resume(missionTrajectoryFrame.value?.sequence||0)
      await startMissionAlgorithm()
    }
    if(['complete','fail','cancel'].includes(action)){
      sessionStore.stop()
      await stopMissionAlgorithm(`任务中心${action}`)
    }
    await load()
    return true
  }catch(error){ElMessage.error(error instanceof Error?error.message:'任务指令执行失败');return false}finally{actionBusy.value=false}
}
async function confirmStart(){
  if(!await runMissionAction('start')||!detail.value?.currentRun)return
  startVisible.value=false
  unityViewportStore.prepareMission(detail.value.mission.id,detail.value.currentRun.id,detail.value.currentRun.runtimeInstanceId)
  await router.push({name:'mission-run',params:{missionId:detail.value.mission.id,runId:detail.value.currentRun.id}})
}
async function openExecution(mission:Mission){
  const loaded=await loadDetail(mission)
  if(!loaded.currentRun){ElMessage.warning('该任务还没有可查看的运行批次');return}
  unityViewportStore.prepareMission(loaded.mission.id,loaded.currentRun.id,loaded.currentRun.runtimeInstanceId)
  await router.push({name:'mission-run',params:{missionId:loaded.mission.id,runId:loaded.currentRun.id}})
}
async function repeatExecution(mission:Mission){
  await loadDetail(mission)
  if(!await runMissionAction('ready')||!detail.value)return
  await openStart(detail.value.mission)
}
async function handleListAction(action:string,mission:Mission){
  if(action==='configure')return openConfig(mission)
  if(action==='view')return openConfig(mission,true)
  if(action==='start')return openStart(mission)
  if(action==='execute')return openExecution(mission)
  if(action==='events'){await loadDetail(mission);eventVisible.value=true;return}
  if(action==='result'){showDeveloping('实验结果分析与导出');return}
  if(action==='delete'){try{await ElMessageBox.confirm(`确认删除任务“${mission.name}”？`,'删除任务',{type:'warning'});await deleteMission(mission.id);await load()}catch{return}}
  if(action==='copy'){const source=await loadDetail(mission);detail.value={...source,mission:{...source.mission,id:0,code:`${source.mission.code}-COPY`,name:`${source.mission.name}（副本）`,status:'DRAFT'}};selectedMission.value=null;configReadonly.value=false;configVisible.value=true;return}
  if(action==='retry')return repeatExecution(mission)
}
function showDeveloping(feature:string){ElMessage.info(`${feature}功能正在开发，当前版本暂未开放`)}
watch([keyword,typeFilter,statusFilter,modeFilter],()=>void load(0))
onMounted(()=>{
  monitoringStore.connectEvents()
  void deviceStore.refresh({page:0,size:100})
  void perceptionStore.refresh()
  void algorithmStore.refreshStatus()
  void load(0)
})
</script>

<template>
  <ConsoleLayout title="任务中心" eyebrow="MISSION EXPERIMENT CENTER">
    <template #actions>
      <button class="mission-header-tool" type="button" @click="showDeveloping('算法注册管理')">
        <Settings2 :size="15" />算法管理
      </button>
    </template>
    <section class="mission-center">
      <header class="mission-center-header">
        <div>
          <span>ALGORITHM · RUN · RESULT</span>
          <h2>算法实验任务与运行批次</h2>
          <p>系统总览与任务中心运行域相互隔离；2D 轨迹和 3D Unity 共享同一任务 RUN。</p>
        </div>
        <button class="primary-action" @click="openConfig()"><Plus :size="18"/>新建实验任务</button>
      </header>

      <div class="mission-summary-grid">
        <article><span class="summary-icon"><Beaker :size="20"/></span><div><span>全部任务模板</span><b>{{ summary.total }}</b><small>支持草稿与重复运行</small></div></article>
        <article><span class="summary-icon ready"><Clock3 :size="20"/></span><div><span>待执行</span><b>{{ summary.ready }}</b><small>可执行简单围捕</small></div></article>
        <article><span class="summary-icon running"><Radio :size="20"/></span><div><span>运行中</span><b>{{ summary.running }}</b><small>{{ missionUnityChannel.connected ? '任务中心 Unity 在线' : '等待任务中心 Unity' }}</small></div></article>
        <article><span class="summary-icon abnormal"><AlertTriangle :size="20"/></span><div><span>异常与终止</span><b>{{ summary.abnormal }}</b><small>保留事件与运行记录</small></div></article>
      </div>

      <AlgorithmMissionControlPanel />

      <AlgorithmMissionStatusPanel />

      <AlgorithmTacticalMap />

      <div class="mission-center-grid">
        <section class="mission-catalog-panel">
          <header class="catalog-heading">
            <div><h3>实验任务</h3><p>任务模板负责配置，运行批次保存每次任务的独立执行记录。</p></div>
            <span><CircleCheck :size="14"/>任务中心独立运行域</span>
          </header>
          <div class="mission-filters">
            <div class="search-field"><Search :size="16"/><input v-model="keyword" placeholder="搜索任务编号、名称、目标或区域"/></div>
            <el-select v-model="typeFilter" clearable placeholder="全部任务类型"><el-option label="协同围捕" value="COOPERATIVE_ENCIRCLEMENT"/><el-option label="目标巡检" value="TARGET_INSPECTION"/><el-option label="路径跟踪" value="PATH_TRACKING"/><el-option label="通信中继" value="COMMUNICATION_RELAY"/><el-option label="自定义" value="CUSTOM"/></el-select>
            <el-select v-model="statusFilter" clearable placeholder="全部状态"><el-option v-for="status in ['DRAFT','READY','RUNNING','PAUSED','COMPLETED','FAILED','CANCELLED']" :key="status" :label="status" :value="status"/></el-select>
            <el-select v-model="modeFilter" clearable placeholder="全部运行模式"><el-option label="ROS / Gazebo" value="ROS_GAZEBO"/><el-option label="Unity 独立" value="UNITY_STANDALONE"/><el-option label="混合镜像" value="HYBRID_MIRROR"/></el-select>
          </div>
          <MissionListPanel :missions="missionStore.records" :loading="missionStore.loading" @action="handleListAction"/>
          <el-pagination class="mission-pagination" background layout="total, prev, pager, next" :total="missionStore.total" :page-size="missionStore.size" :current-page="missionStore.page+1" @current-change="load($event-1)"/>
        </section>

        <aside class="mission-side-stack">
          <section class="mission-side-panel">
            <header><div><h3>算法库</h3><p>统一适配器接入，任务页面不直接绑定算法实现。</p></div><button @click="showDeveloping('算法注册管理')">管理</button></header>
            <article class="algorithm-card available">
              <div class="algorithm-icon"><Radio :size="20"/></div>
              <div>
                <b>后端模拟闭环</b>
                <span>{{ missionAlgorithmRun?.commandId || '等待任务启动' }}</span>
                <p>{{ missionAlgorithmRun?.message || `感知：${perceptionStore.onlineSensorCount}/${perceptionStore.sensors.length} 传感器在线，${perceptionStore.hostileTargetCount} 个敌方目标` }}</p>
              </div>
              <em>{{ algorithmStatusLabel(missionAlgorithmRun?.status) }}</em>
            </article>
            <article class="algorithm-card available">
              <div class="algorithm-icon"><Waves :size="20"/></div>
              <div><b>Unity 默认简单围捕</b><span>UnityNativeAdapter · v1.0</span><p>支持开始、暂停、继续、终止和实时轨迹。</p></div>
              <em>可执行</em>
            </article>
            <article class="algorithm-card" @click="showDeveloping('PSO 协同围捕算法')">
              <div class="algorithm-icon"><Cpu :size="20"/></div>
              <div><b>PSO 协同围捕</b><span>ExternalAdapter · v2.3</span><p>粒子群编队分配与闭合控制。</p></div>
              <em>开发中</em>
            </article>
            <article class="algorithm-card" @click="showDeveloping('强化学习围捕策略')">
              <div class="algorithm-icon"><Bot :size="20"/></div>
              <div><b>强化学习围捕策略</b><span>ModelGateway · v0.8</span><p>策略模型推理与安全约束适配。</p></div>
              <em>开发中</em>
            </article>
          </section>

          <section class="mission-side-panel">
            <header><div><h3>最近运行</h3><p>显示当前列表中的最近任务批次。</p></div><FlaskConical :size="17"/></header>
            <div v-if="recentRuns.length" class="recent-run-list">
              <button v-for="mission in recentRuns" :key="mission.id" @click="['RUNNING','PAUSED'].includes(mission.status) ? openExecution(mission) : showDeveloping('历史运行结果')">
                <span>{{ mission.code }}</span><b>{{ mission.name }}</b><em :class="mission.status.toLowerCase()">{{ mission.status }}</em>
              </button>
            </div>
            <p v-else class="empty-runs">暂无运行批次，完成任务配置后可启动实验。</p>
          </section>

          <section class="mission-side-panel capability-panel">
            <header><div><h3>当前能力</h3><p>仅展示已经接通真实链路的功能。</p></div></header>
            <ul>
              <li><CircleCheck :size="14"/>任务新建、编辑、自动编组和任务保存</li>
              <li><CircleCheck :size="14"/>执行检查、开始、暂停、继续和终止任务</li>
              <li><CircleCheck :size="14"/>同一 RUN 的 2D 轨迹与 3D Unity 切换</li>
              <li><CircleCheck :size="14"/>任务事件与设备快捷指令</li>
            </ul>
            <button @click="showDeveloping('结果对比与数据包导出')">结果对比 / 导出正在开发</button>
          </section>
        </aside>
      </div>
    </section>
    <MissionConfigDialog v-model="configVisible" :detail="detail" :devices="deviceStore.records" :readonly="configReadonly" :saving="saving" @save="save"/>
    <MissionStartCheckDialog v-model="startVisible" :check="preflight" :trajectory-live="trajectoryLive" :loading="preflightLoading" @confirm="confirmStart"/>
    <MissionEventDrawer v-model="eventVisible" :mission-id="detail?.mission.id||null" :run-id="detail?.currentRun?.id"/>
  </ConsoleLayout>
</template>

<style scoped>
.mission-center{max-width:1680px;margin:0 auto;padding:2px}.mission-header-tool{display:inline-flex;align-items:center;gap:6px;height:36px;padding:0 12px;color:#cfe9e6;background:rgba(108,228,213,.07);border:1px solid rgba(108,228,213,.22);border-radius:5px;cursor:pointer}.mission-center-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;padding:15px 17px;background:linear-gradient(90deg,rgba(5,30,40,.92),rgba(4,18,27,.88));border:1px solid rgba(80,191,218,.22);border-radius:8px}.mission-center-header>div>span{color:#4dd3e7;font-size:10px;font-weight:900;letter-spacing:.14em}.mission-center-header h2{font-size:23px;margin:4px 0}.mission-center-header p{color:#799ba0;font-size:12px;margin:5px 0 0}.primary-action{display:flex;align-items:center;gap:7px;height:40px;padding:0 17px;border:1px solid #6ce4d5;border-radius:6px;background:linear-gradient(135deg,#247988,#155563);color:#ecffff;cursor:pointer}.mission-summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px}.mission-summary-grid article{display:flex;align-items:center;gap:12px;padding:14px;border:1px solid rgba(108,228,213,.18);border-radius:8px;background:linear-gradient(145deg,#061d27,#04141c)}.summary-icon{display:grid;width:42px;height:42px;place-items:center;color:#56dbea;background:rgba(61,190,218,.09);border:1px solid rgba(61,190,218,.22);border-radius:7px}.summary-icon.ready{color:#ffc93e;border-color:rgba(255,201,62,.25);background:rgba(255,201,62,.07)}.summary-icon.running{color:#55e7a7;border-color:rgba(85,231,167,.25);background:rgba(85,231,167,.07)}.summary-icon.abnormal{color:#ff7474;border-color:rgba(255,116,116,.25);background:rgba(255,116,116,.07)}.mission-summary-grid article div span,.mission-summary-grid article div b,.mission-summary-grid article div small{display:block}.mission-summary-grid article div span{color:#83a5aa;font-size:11px}.mission-summary-grid article div b{font-size:22px;margin-top:2px;color:#e8f8f7}.mission-summary-grid article div small{color:#5e8186;font-size:9px;margin-top:2px}.mission-center-grid{display:grid;grid-template-columns:minmax(0,1fr) 350px;gap:11px;align-items:start}.mission-catalog-panel,.mission-side-panel{background:linear-gradient(145deg,rgba(5,26,36,.96),rgba(3,17,25,.96));border:1px solid rgba(75,174,201,.22);border-radius:9px}.mission-catalog-panel{padding:13px}.catalog-heading,.mission-side-panel>header{display:flex;align-items:center;justify-content:space-between;gap:12px}.catalog-heading{padding:2px 2px 12px;border-bottom:1px solid rgba(79,169,190,.16)}.catalog-heading h3,.mission-side-panel h3{margin:0;color:#efffff;font-size:16px}.catalog-heading p,.mission-side-panel header p{margin:4px 0 0;color:#6f9297;font-size:10px}.catalog-heading>span{display:inline-flex;align-items:center;gap:5px;color:#68e0a5;font-size:10px}.mission-filters{display:grid;grid-template-columns:minmax(260px,1fr) repeat(3,155px);gap:8px;margin:12px 0}.search-field{display:flex;align-items:center;gap:8px;height:36px;border:1px solid #254b55;border-radius:5px;padding:0 11px;background:#061b24;color:#668e94}.search-field input{flex:1;border:0;outline:0;background:transparent;color:#e4f4f3}.mission-pagination{justify-content:flex-end;margin-top:14px}.mission-side-stack{display:grid;gap:10px}.mission-side-panel{padding:13px}.mission-side-panel>header{margin-bottom:11px}.mission-side-panel>header>button,.capability-panel>button{height:28px;padding:0 10px;color:#bcd9d7;background:#08242d;border:1px solid #28535d;border-radius:4px;cursor:pointer}.algorithm-card{display:grid;grid-template-columns:38px minmax(0,1fr) auto;gap:9px;align-items:start;padding:10px;margin-top:7px;background:rgba(72,145,158,.045);border:1px solid rgba(81,159,175,.13);border-radius:6px;cursor:pointer}.algorithm-card.available{border-color:rgba(85,231,167,.24)}.algorithm-icon{display:grid;width:38px;height:38px;place-items:center;color:#57d8e6;background:rgba(68,190,213,.08);border:1px solid rgba(68,190,213,.18);border-radius:6px}.algorithm-card b,.algorithm-card span,.algorithm-card p{display:block}.algorithm-card b{color:#dff7f5;font-size:12px}.algorithm-card span{margin-top:3px;color:#6f9297;font-size:9px}.algorithm-card p{margin:5px 0 0;color:#829fa2;font-size:9px}.algorithm-card em{font-style:normal;color:#ffc85a;font-size:9px}.algorithm-card.available em{color:#55e7a7}.recent-run-list{display:grid;gap:6px}.recent-run-list button{position:relative;display:grid;width:100%;grid-template-columns:1fr auto;gap:2px 8px;text-align:left;padding:9px 10px;background:rgba(68,145,159,.045);border:1px solid rgba(81,159,175,.13);border-radius:5px;color:#dbeeed;cursor:pointer}.recent-run-list button span{color:#50d4e8;font-size:9px}.recent-run-list button b{grid-column:1;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.recent-run-list button em{grid-column:2;grid-row:1/3;align-self:center;color:#8facaf;font-size:9px;font-style:normal}.recent-run-list button em.running,.recent-run-list button em.paused{color:#55e7a7}.recent-run-list button em.failed,.recent-run-list button em.cancelled{color:#ff7474}.empty-runs{color:#698c90;font-size:10px}.capability-panel ul{display:grid;gap:8px;padding:0;margin:0 0 11px;list-style:none}.capability-panel li{display:flex;align-items:center;gap:7px;color:#9ebbbb;font-size:10px}.capability-panel li svg{color:#55e7a7}.capability-panel>button{width:100%;height:34px;color:#7f9da0}.mission-center :deep(.el-select__wrapper){min-height:36px;background:#061b24;box-shadow:0 0 0 1px #254b55 inset}.mission-center :deep(.el-select__placeholder),.mission-center :deep(.el-select__selected-item){color:#89a6aa}@media(max-width:1300px){.mission-center-grid{grid-template-columns:1fr}.mission-side-stack{grid-template-columns:repeat(3,minmax(0,1fr))}.mission-filters{grid-template-columns:1fr 1fr}.mission-summary-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:820px){.mission-center-header{align-items:flex-start;flex-direction:column}.mission-summary-grid,.mission-side-stack,.mission-filters{grid-template-columns:1fr}}
</style>
