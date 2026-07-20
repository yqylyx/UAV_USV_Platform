import { reactive, ref, watch } from 'vue'

import type {
  AlgorithmPositionPayload,
  AlgorithmPositionSource,
  AlgorithmVehiclePosition,
} from '@/api/algorithm'
import type { AlgorithmMissionType } from '@/types/algorithmMission'

export type AlgorithmDemoControlState = 'READY' | 'RUNNING' | 'STOPPED'

export interface AlgorithmPositionForm {
  x: number | null
  y: number | null
  z: number | null
  heading: number | null
}

export interface AlgorithmManualVehiclePositionForm {
  vehicleId: string
  position: AlgorithmPositionForm
}

function createEmptyPosition(): AlgorithmPositionForm {
  return {
    x: null,
    y: null,
    z: null,
    heading: null,
  }
}

function clearPosition(position: AlgorithmPositionForm) {
  position.x = null
  position.y = null
  position.z = null
  position.heading = null
}

export function isCompletePosition(position: AlgorithmPositionForm): position is {
  x: number
  y: number
  z: number
  heading: number
} {
  return (
    Number.isFinite(position.x) &&
    Number.isFinite(position.y) &&
    Number.isFinite(position.z) &&
    Number.isFinite(position.heading)
  )
}

export function toAlgorithmPosition(position: AlgorithmPositionForm): AlgorithmPositionPayload | null {
  if (!isCompletePosition(position)) return null

  return {
    x: position.x,
    y: position.y,
    z: position.z,
    heading: position.heading,
  }
}

const selectedMissionType = ref<AlgorithmMissionType>('CAPTURE')
const controlState = ref<AlgorithmDemoControlState>('READY')
const currentCommandId = ref<string | null>(null)
const positionSource = ref<AlgorithmPositionSource>('REALTIME')
const manualVehiclePositions = reactive<AlgorithmManualVehiclePositionForm[]>([])
const submittedPositionSource = ref<AlgorithmPositionSource | null>(null)
const submittedVehicleIds = ref<string[]>([])
const submittedManualVehiclePositions = ref<AlgorithmVehiclePosition[]>([])

const captureForm = reactive({
  targetId: 'target_01',
  targetPosition: createEmptyPosition(),
  uavIds: ['uav_01', 'uav_02', 'uav_03'],
  usvIds: ['usv_01', 'usv_02'],
  captureRadius: 60,
  minimumAgents: 4,
  dynamicReassignment: true,
})

const escortForm = reactive({
  escortTargetId: 'escort_target_01',
  threatTargetId: 'enemy_01',
  targetPosition: createEmptyPosition(),
  threatPosition: createEmptyPosition(),
  uavIds: ['uav_01', 'uav_02', 'uav_03'],
  usvIds: ['usv_01', 'usv_02', 'usv_03'],
  escortRadius: 45,
  defenseDistance: 30,
  threatDirection: 'FRONT',
})

function selectedVehicleIds() {
  const form = selectedMissionType.value === 'CAPTURE' ? captureForm : escortForm
  return [...form.uavIds, ...form.usvIds]
}

function syncManualVehiclePositions() {
  if (positionSource.value !== 'MANUAL') return

  const selectedIds = selectedVehicleIds()
  const selectedIdSet = new Set(selectedIds)

  for (let index = manualVehiclePositions.length - 1; index >= 0; index -= 1) {
    const item = manualVehiclePositions[index]
    if (item && !selectedIdSet.has(item.vehicleId)) {
      manualVehiclePositions.splice(index, 1)
    }
  }

  for (const vehicleId of selectedIds) {
    if (!manualVehiclePositions.some((item) => item.vehicleId === vehicleId)) {
      manualVehiclePositions.push({
        vehicleId,
        position: createEmptyPosition(),
      })
    }
  }
}

function getManualVehiclePosition(vehicleId: string) {
  let item = manualVehiclePositions.find((position) => position.vehicleId === vehicleId)
  if (!item) {
    item = {
      vehicleId,
      position: createEmptyPosition(),
    }
    manualVehiclePositions.push(item)
  }
  return item
}

function copyManualVehiclePositions(items: AlgorithmVehiclePosition[]) {
  return items.map((item) => ({
    vehicleId: item.vehicleId,
    position: {
      x: item.position.x,
      y: item.position.y,
      z: item.position.z,
      heading: item.position.heading,
    },
  }))
}

function startDemo(
  commandId: string,
  snapshot: {
    positionSource: AlgorithmPositionSource
    vehicleIds: string[]
    manualVehiclePositions?: AlgorithmVehiclePosition[]
  },
) {
  currentCommandId.value = commandId
  controlState.value = 'RUNNING'
  submittedPositionSource.value = snapshot.positionSource
  submittedVehicleIds.value = [...snapshot.vehicleIds]
  submittedManualVehiclePositions.value = copyManualVehiclePositions(snapshot.manualVehiclePositions ?? [])
}

function stopDemo() {
  controlState.value = 'STOPPED'
}

function resetDemo() {
  controlState.value = 'READY'
  currentCommandId.value = null
  positionSource.value = 'REALTIME'
  manualVehiclePositions.splice(0, manualVehiclePositions.length)
  submittedPositionSource.value = null
  submittedVehicleIds.value = []
  submittedManualVehiclePositions.value = []

  selectedMissionType.value = 'CAPTURE'

  captureForm.targetId = 'target_01'
  clearPosition(captureForm.targetPosition)
  captureForm.uavIds = ['uav_01', 'uav_02', 'uav_03']
  captureForm.usvIds = ['usv_01', 'usv_02']
  captureForm.captureRadius = 60
  captureForm.minimumAgents = 4
  captureForm.dynamicReassignment = true

  escortForm.escortTargetId = 'escort_target_01'
  escortForm.threatTargetId = 'enemy_01'
  clearPosition(escortForm.targetPosition)
  clearPosition(escortForm.threatPosition)
  escortForm.uavIds = ['uav_01', 'uav_02', 'uav_03']
  escortForm.usvIds = ['usv_01', 'usv_02', 'usv_03']
  escortForm.escortRadius = 45
  escortForm.defenseDistance = 30
  escortForm.threatDirection = 'FRONT'
}

watch(
  [
    positionSource,
    selectedMissionType,
    () => [...captureForm.uavIds],
    () => [...captureForm.usvIds],
    () => [...escortForm.uavIds],
    () => [...escortForm.usvIds],
  ],
  syncManualVehiclePositions,
  { immediate: true },
)

export function useAlgorithmMissionDemo() {
  return {
    selectedMissionType,
    controlState,
    currentCommandId,
    positionSource,
    manualVehiclePositions,
    submittedPositionSource,
    submittedVehicleIds,
    submittedManualVehiclePositions,
    captureForm,
    escortForm,
    getManualVehiclePosition,
    syncManualVehiclePositions,
    startDemo,
    stopDemo,
    resetDemo,
  }
}
