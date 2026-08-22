import type { UnityTrajectoryAgent, UnityTrajectoryFrame } from '@/stores/trajectory'
import type { GatewayEnvelope, PoseBatchPayload, VehiclePoseSample } from '@/types/realtime'

export type RealtimeRunScopePolicy = 'STRICT' | 'ALLOW_MISSING'

export type RealtimeTrajectoryContext = {
  missionId?: number | string | null
  runId?: number | string | null
  phase?: string | null
}

export type MissionCenterPoseFrameContext = RealtimeTrajectoryContext & {
  algorithmCode?: string | null
  route?: Array<{ x: number; y: number }>
  obstacles?: unknown[]
}

export type SystemOverviewPose = {
  deviceCode: string
  deviceType: string
  type: string
  state: string
  valid: boolean
  position: [number, number, number]
  eastM: number
  northM: number
  upM: number
  headingDeg: number
  x: number
  y: number
  z: number
  yaw: number
}

function finite(value: unknown, fallback = 0) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function normalizedRunId(value: unknown) {
  const text = String(value ?? '').trim()
  return text || null
}

export function normalizeRealtimeDeviceCode(value: unknown) {
  return String(value ?? '').trim().toLowerCase()
}

export function isRealtimeEnvelopeApplicable(
  envelope: Pick<GatewayEnvelope, 'runId'> | null | undefined,
  context: RealtimeTrajectoryContext = {},
  policy: RealtimeRunScopePolicy = 'ALLOW_MISSING',
) {
  if (!envelope) return false
  const envelopeRunId = normalizedRunId(envelope.runId)
  const contextRunId = normalizedRunId(context.runId)
  if (policy === 'STRICT') {
    return !!envelopeRunId && !!contextRunId && envelopeRunId === contextRunId
  }
  if (!envelopeRunId) return !!contextRunId
  return !!contextRunId && envelopeRunId === contextRunId
}

function poseDeviceType(deviceCode: string): UnityTrajectoryAgent['type'] {
  const code = normalizeRealtimeDeviceCode(deviceCode)
  if (code.startsWith('usv')) return 'USV'
  if (code.startsWith('target') || code.startsWith('tgt')) return 'TARGET'
  return 'UAV'
}

function validPoseSample(sample: VehiclePoseSample) {
  const position = sample.localPositionEnuM
  return !!position
    && sample.fresh !== false
    && sample.positionValid !== false
    && Number.isFinite(position.x)
    && Number.isFinite(position.y)
    && Number.isFinite(position.z)
    && !!normalizeRealtimeDeviceCode(sample.deviceCode)
}

function poseState(sample: VehiclePoseSample) {
  if (sample.fresh === false || sample.positionValid === false) return 'STALE'
  return 'ACTIVE'
}

export function poseBatchTimestampMs(envelope: GatewayEnvelope<PoseBatchPayload> | null | undefined) {
  if (!envelope) return 0
  return Date.parse(envelope.timestamp)
    || Date.parse(envelope.payload.snapshotTime ?? '')
    || 0
}

export function poseBatchValidVehicleCount(envelope: GatewayEnvelope<PoseBatchPayload> | null | undefined) {
  return envelope?.payload.vehicles?.filter(validPoseSample).length ?? 0
}

export function isPoseBatchLive(
  envelope: GatewayEnvelope<PoseBatchPayload> | null | undefined,
  now = Date.now(),
  maxAgeMs = 3000,
) {
  if (!envelope || poseBatchValidVehicleCount(envelope) === 0) return false
  const timestampMs = poseBatchTimestampMs(envelope)
  if (timestampMs <= 0) return true
  return now - timestampMs <= maxAgeMs
}

export function poseBatchToTrajectoryPayload(
  envelope: GatewayEnvelope<PoseBatchPayload> | null | undefined,
  context: RealtimeTrajectoryContext = {},
) {
  const vehicles = envelope?.payload.vehicles?.filter(validPoseSample) ?? []
  if (!envelope || vehicles.length === 0) return null
  const receivedAt = poseBatchTimestampMs(envelope) || Date.now()
  const runId = envelope.runId ?? context.runId ?? null
  return {
    missionId: context.missionId ?? null,
    runId,
    sequence: envelope.sequence,
    timestamp: receivedAt,
    source: envelope.source || 'ros-gateway-v1',
    coordinateSystem: 'ROS_ENU',
    mission: {
      phase: context.phase || 'ROS_GATEWAY_V1',
      elapsed: 0,
      captureRadius: 16,
      defenseRadius: 18,
      captureReady: false,
      formationHolding: false,
    },
    agents: vehicles.map((vehicle) => {
      const position = vehicle.localPositionEnuM!
      return {
        code: normalizeRealtimeDeviceCode(vehicle.deviceCode),
        type: poseDeviceType(vehicle.deviceCode),
        x: finite(position.x),
        y: finite(position.z),
        z: finite(position.y),
        yaw: finite(vehicle.headingDeg),
        state: poseState(vehicle),
      }
    }),
  }
}

export function poseBatchToTrajectoryFrame(
  envelope: GatewayEnvelope<PoseBatchPayload> | null | undefined,
  context: RealtimeTrajectoryContext = {},
): UnityTrajectoryFrame | null {
  const payload = poseBatchToTrajectoryPayload(envelope, context)
  if (!payload) return null
  return {
    sequence: payload.sequence,
    source: payload.source,
    coordinateSystem: payload.coordinateSystem,
    mission: payload.mission,
    agents: payload.agents,
    receivedAt: Number(payload.timestamp) || Date.now(),
  }
}

export function trajectoryFrameToSystemOverviewPoseFrame(
  frame: UnityTrajectoryFrame | null | undefined,
  context: RealtimeTrajectoryContext = {},
) {
  if (!frame?.agents.length) return null
  const runId = context.runId ?? null
  const poses: SystemOverviewPose[] = frame.agents.map((agent) => {
    const eastM = finite(agent.x)
    const northM = finite(agent.z)
    const upM = finite(agent.y)
    return {
      deviceCode: agent.code,
      deviceType: agent.type,
      type: agent.type,
      state: agent.state,
      valid: true,
      position: [eastM, northM, upM],
      eastM,
      northM,
      upM,
      headingDeg: finite(agent.yaw),
      x: eastM,
      y: northM,
      z: upM,
      yaw: finite(agent.yaw),
    }
  })
  return {
    runtimeMode: 'REAL',
    missionId: context.missionId ?? null,
    runId,
    sequence: frame.sequence,
    source: frame.source,
    coordinateFrame: 'GLOBAL_ENU',
    coordinateSystem: frame.coordinateSystem,
    timestamp: frame.receivedAt,
    timestampMs: frame.receivedAt,
    poses,
  }
}

export function trajectoryFrameToMissionCenterPoseFrame(
  frame: UnityTrajectoryFrame | null | undefined,
  context: MissionCenterPoseFrameContext = {},
) {
  if (!frame?.agents.length) return null
  const runId = Number(context.runId)
  return {
    algorithmCode: String(context.algorithmCode || 'GB_SFLA_CS'),
    runId: Number.isFinite(runId) ? runId : 0,
    sequence: frame.sequence,
    timestamp: frame.receivedAt,
    phase: frame.mission.phase,
    agents: frame.agents
      .filter(agent => agent.type === 'UAV' || agent.type === 'USV')
      .map(agent => ({
        code: agent.code,
        type: agent.type,
        x: finite(agent.x),
        y: finite(agent.z),
        z: finite(agent.y),
        heading: finite(agent.yaw),
      })),
    targets: frame.agents
      .filter(agent => agent.type === 'TARGET')
      .map(agent => ({
        code: agent.code,
        type: 'TARGET',
        x: finite(agent.x),
        y: finite(agent.z),
        z: finite(agent.y),
        heading: finite(agent.yaw),
        visible: true,
      })),
    route: context.route ?? [],
    obstacles: context.obstacles ?? [],
  }
}
