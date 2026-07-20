import { reactive, ref } from 'vue'

import type { AlgorithmMissionType } from '@/types/algorithmMission'

export type AlgorithmDemoControlState = 'READY' | 'RUNNING' | 'STOPPED'

const selectedMissionType = ref<AlgorithmMissionType>('CAPTURE')
const controlState = ref<AlgorithmDemoControlState>('READY')
const currentCommandId = ref<string | null>(null)

const captureForm = reactive({
  targetId: 'target_01',
  uavIds: ['uav_01', 'uav_02', 'uav_03'],
  usvIds: ['usv_01', 'usv_02'],
  captureRadius: 60,
  minimumAgents: 4,
  dynamicReassignment: true,
})

const escortForm = reactive({
  escortTargetId: 'escort_target_01',
  threatTargetId: 'enemy_01',
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
  captureForm.uavIds = ['uav_01', 'uav_02', 'uav_03']
  captureForm.usvIds = ['usv_01', 'usv_02']
  captureForm.captureRadius = 60
  captureForm.minimumAgents = 4
  captureForm.dynamicReassignment = true

  escortForm.escortTargetId = 'escort_target_01'
  escortForm.threatTargetId = 'enemy_01'
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
