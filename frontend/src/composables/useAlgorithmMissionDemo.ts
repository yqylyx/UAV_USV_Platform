import { reactive, ref } from 'vue'

import type { AlgorithmMissionType } from '@/types/algorithmMission'

export type AlgorithmDemoControlState = 'READY' | 'RUNNING' | 'STOPPED'

export interface AlgorithmPositionForm {
  x: number | null
  y: number | null
  z: number | null
  heading: number | null
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

export function toAlgorithmPosition(position: AlgorithmPositionForm) {
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

function startDemo(commandId: string) {
  currentCommandId.value = commandId
  controlState.value = 'RUNNING'
}

function stopDemo() {
  controlState.value = 'STOPPED'
}

function resetDemo() {
  controlState.value = 'READY'
  currentCommandId.value = null

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

export function useAlgorithmMissionDemo() {
  return {
    selectedMissionType,
    controlState,
    currentCommandId,
    captureForm,
    escortForm,
    startDemo,
    stopDemo,
    resetDemo,
  }
}
