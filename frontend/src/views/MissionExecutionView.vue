<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import MissionEventDrawer from '@/components/mission/MissionEventDrawer.vue'
import MissionExecutionOverlay from '@/components/mission/MissionExecutionOverlay.vue'
import type { VehicleQuickCommand } from '@/components/control/VehicleQuickControl.vue'
import { executeMissionAction, fetchMission } from '@/api/mission'
import type { MissionAction } from '@/api/mission'
import { issueRuntimeCommand } from '@/api/runtimeControl'
import type { RuntimeCommandStatus, RuntimeCommandType } from '@/api/runtimeControl'
import { useMissionTrajectorySessionStore } from '@/stores/missionTrajectorySession'
import { useMonitoringStore } from '@/stores/monitoring'
import { useTrajectoryStore } from '@/stores/trajectory'
import { useUnityBridgeStore } from '@/stores/unityBridge'
import { useUnityViewportStore } from '@/stores/unityViewport'
import type { MissionDetail } from '@/types/mission'
import type { RuntimeNode } from '@/types/monitoring'

const route = useRoute()
const router = useRouter()
const monitoringStore = useMonitoringStore()
const trajectoryStore = useTrajectoryStore()
const unityBridgeStore = useUnityBridgeStore()
const sessionStore = useMissionTrajectorySessionStore()
const unityViewportStore = useUnityViewportStore()

const detail = ref<MissionDetail | null>(null)
const selectedDeviceCode = ref('uav-01')
const commandFeedback = ref<Record<string, RuntimeCommandStatus | undefined>>({})
const operationalStates = ref<Record<string, string | undefined>>({})
const busy = ref(false)
const eventVisible = ref(false)
const mode = ref<'2d' | '3d'>('2d')
const missionId = computed(() => Number(route.params.missionId))
const runId = computed(() => Number(route.params.runId))
const unityChannel = computed(() => unityBridgeStore.channels.MISSION_CENTER)
const trajectoryFrame = computed(() => trajectoryStore.channels.MISSION_CENTER.frame)

const runtimeNodes = computed<RuntimeNode[]>(() => {
  const frame = trajectoryFrame.value
  if (!frame) return monitoringStore.nodes.filter(node => node.type === 'UAV' || node.type === 'USV')
  return frame.agents
    .filter(agent => agent.type === 'UAV' || agent.type === 'USV')
    .map((agent, index) => {
      const existing = monitoringStore.nodes.find(node => node.code.toLowerCase() === agent.code.toLowerCase())
      return {
        id: existing?.id ?? -(index + 1),
        code: agent.code,
        name: existing?.name ?? `协同${agent.type === 'UAV' ? '无人机' : '无人艇'} ${agent.code.replace(/[^0-9]/g, '')}`,
        type: agent.type as 'UAV' | 'USV',
        status: 'ONLINE',
        host: null,
        port: null,
        endpoint: 'unity://mission-center',
        rosNamespace: null,
        lastHeartbeatAt: new Date(frame.receivedAt).toISOString(),
        heartbeatAgeSeconds: Math.max(0, Math.round((Date.now() - frame.receivedAt) / 1000)),
        source: 'UNITY_WEBGL',
        instanceId: unityViewportStore.missionInstanceId,
        positionX: agent.x,
        positionY: agent.y,
        positionZ: agent.z,
        detail: agent.state,
      }
    })
})

watch(trajectoryFrame, frame => {
  if (!frame) return
  const next = { ...operationalStates.value }
  for (const agent of frame.agents) {
    if (agent.type === 'UAV' || agent.type === 'USV') next[agent.code.toLowerCase()] = agent.state
  }
  operationalStates.value = next
  if (!runtimeNodes.value.some(node => node.code.toLowerCase() === selectedDeviceCode.value.toLowerCase())) {
    selectedDeviceCode.value = runtimeNodes.value[0]?.code ?? ''
  }
}, { immediate: true })

function missionUnityCommand(action: MissionAction) {
  return { start: 'missionStart', pause: 'missionPause', resume: 'missionResume', complete: 'missionComplete', fail: 'missionFail', cancel: 'missionCancel', ready: 'missionResume' }[action]
}

function vehicleUnityCommand(commandType: RuntimeCommandType) {
  const commands: Partial<Record<RuntimeCommandType, string>> = {
    UAV_TAKEOFF: 'uavTakeoff', UAV_HOVER: 'uavHover', UAV_RESUME: 'uavResume', UAV_RETURN: 'uavReturn', UAV_LAND: 'uavLand', UAV_EMERGENCY_LAND: 'uavEmergencyLand',
    USV_DEPART: 'usvDepart', USV_HOLD: 'usvHold', USV_RESUME: 'usvResume', USV_RETURN: 'usvReturn', USV_STOP: 'usvStop', USV_EMERGENCY_STOP: 'usvEmergencyStop',
  }
  return commands[commandType] ?? commandType.toLowerCase()
}

async function loadDetail() {
  if (!Number.isFinite(missionId.value) || !Number.isFinite(runId.value)) throw new Error('任务运行地址无效')
  const loaded = await fetchMission(missionId.value)
  const requestedRun = loaded.runs.find(run => run.id === runId.value) ?? (loaded.currentRun?.id === runId.value ? loaded.currentRun : null)
  if (!requestedRun) throw new Error('未找到该任务运行批次')
  loaded.currentRun = requestedRun
  detail.value = loaded
  sessionStore.bind(loaded.mission.id, requestedRun.id)
  unityViewportStore.prepareMission(loaded.mission.id, requestedRun.id, requestedRun.runtimeInstanceId)
}

async function runMissionAction(action: 'pause' | 'resume' | 'complete' | 'cancel') {
  if (!detail.value) return
  if (action === 'cancel') {
    try {
      await ElMessageBox.confirm('确认终止当前任务运行？该操作只影响任务中心，不影响系统总览。', '终止任务', { type: 'warning', confirmButtonText: '确认终止', cancelButtonText: '取消' })
    } catch { return }
  }
  busy.value = true
  try {
    if (!unityChannel.value.connected || !unityChannel.value.controlsReady) throw new Error('任务中心 Unity 指令桥尚未就绪')
    const result = await executeMissionAction(detail.value.mission.id, action, 'MISSION_CONTROL', unityViewportStore.missionInstanceId)
    if (result.command) {
      if (result.command.status === 'FAILED' || result.command.status === 'TIMEOUT') throw new Error(result.command.detail || '任务指令创建失败')
      const ack = await unityBridgeStore.sendControlCommandAndWaitFor('MISSION_CENTER', missionUnityCommand(action), '', result.command.commandKey)
      if (!ack.success) throw new Error(ack.status || 'Unity 未确认任务指令')
    }
    if (action === 'pause') sessionStore.pause()
    if (action === 'resume') sessionStore.resume(trajectoryFrame.value?.sequence ?? 0)
    if (action === 'complete' || action === 'cancel') sessionStore.stop()
    await loadDetail()
    ElMessage.success(action === 'pause' ? '任务已暂停' : action === 'resume' ? '任务已继续' : action === 'complete' ? '任务已完成' : '任务已终止')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '任务指令执行失败')
  } finally { busy.value = false }
}

async function sendVehicleCommand(command: VehicleQuickCommand) {
  if (!detail.value?.currentRun || !command.deviceCodes.length) return
  if (!unityChannel.value.connected || !unityChannel.value.controlsReady) {
    ElMessage.error('任务中心 Unity 指令桥尚未就绪')
    return
  }
  busy.value = true
  let acknowledged = 0
  try {
    for (const code of command.deviceCodes) {
      const key = code.toLowerCase()
      commandFeedback.value = { ...commandFeedback.value, [key]: 'PENDING' }
      try {
        const result = await issueRuntimeCommand({
          commandType: command.commandType,
          runId: detail.value.currentRun.id,
          deviceCode: key,
          payload: JSON.stringify({ source: 'MISSION_CONTROL', action: vehicleUnityCommand(command.commandType) }),
          detail: `${command.label} / ${key}`,
          runtimeScope: 'MISSION_CENTER',
          runtimeInstanceId: unityViewportStore.missionInstanceId,
        })
        if (result.status === 'FAILED' || result.status === 'TIMEOUT') throw new Error(result.detail)
        const ack = await unityBridgeStore.sendControlCommandAndWaitFor('MISSION_CENTER', vehicleUnityCommand(command.commandType), key, result.commandKey)
        commandFeedback.value = { ...commandFeedback.value, [key]: ack.success ? 'ACKNOWLEDGED' : 'FAILED' }
        if (ack.success) acknowledged += 1
      } catch {
        commandFeedback.value = { ...commandFeedback.value, [key]: 'FAILED' }
      }
    }
    if (acknowledged === command.deviceCodes.length) ElMessage.success(`${command.label}：${acknowledged}/${command.deviceCodes.length} 台已确认`)
    else ElMessage.error(`${command.label}：成功 ${acknowledged}，失败 ${command.deviceCodes.length - acknowledged}`)
  } finally { busy.value = false }
}

function changeMode(next: '2d' | '3d') {
  mode.value = next
  if (next === '3d') unityViewportStore.show('mission-execution')
  else unityViewportStore.park()
}

async function closeExecution() {
  unityViewportStore.park()
  await router.push({ name: 'missions' })
}

onMounted(async () => {
  unityViewportStore.park()
  monitoringStore.connectEvents()
  await monitoringStore.refresh({}, true)
  try { await loadDetail() } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '任务运行加载失败')
    await router.replace({ name: 'missions' })
  }
})
onBeforeUnmount(() => unityViewportStore.park())
</script>

<template>
  <MissionExecutionOverlay
    v-if="detail"
    :detail="detail"
    :nodes="runtimeNodes"
    :trajectory-frame="trajectoryFrame"
    :session-state="sessionStore.state"
    :session-revision="sessionStore.revision"
    :selected-device-code="selectedDeviceCode"
    :feedback="commandFeedback"
    :operational-states="operationalStates"
    :busy="busy"
    @close="closeExecution"
    @select="selectedDeviceCode = $event"
    @vehicle-command="sendVehicleCommand"
    @mission-action="runMissionAction"
    @events="eventVisible = true"
    @mode-change="changeMode"
  />
  <MissionEventDrawer v-model="eventVisible" :mission-id="detail?.mission.id ?? null" :run-id="detail?.currentRun?.id" />
</template>
