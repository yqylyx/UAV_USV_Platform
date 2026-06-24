export type SimulationStatus = 'STARTING' | 'RUNNING' | 'PARTIAL' | 'STOPPING' | 'STOPPED' | 'FAILED'

export interface RuntimeControlState {
  sessionKey: string | null
  status: SimulationStatus
  rosOnline: boolean
  unityOnline: boolean
  rosManaged: boolean
  unityManaged: boolean
  controllable: boolean
  startedAt: string | null
  message: string
}
