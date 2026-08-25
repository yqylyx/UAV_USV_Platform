import { deriveAdaptiveScenarioPlan } from './adaptiveScenarioPlan'

export interface GridScenarioPose {
  deviceCode: string
  deviceType: 'UAV' | 'USV' | 'TARGET'
  eastM: number
  northM: number
  upM: number
  headingDeg: number
  speedMps: number
  state: string
  valid: boolean
  targetType?: string
}

export interface GridLayoutOptions {
  uavCount: number
  usvCount: number
  fleetOrigin: {
    eastM: number
    northM: number
    upM: number
  }
  uavSpeedMps: number
  usvSpeedMps: number
  captureMode?: boolean
  seed?: number
}

function gridAxis(index: number, count: number, min: number, max: number) {
  if (count <= 1) return (min + max) / 2
  return min + (max - min) * index / (count - 1)
}

function appendGrid(
  poses: GridScenarioPose[],
  type: 'UAV' | 'USV',
  count: number,
  xMin: number,
  xMax: number,
  speedMps: number,
  origin: GridLayoutOptions['fleetOrigin'],
) {
  const columns = Math.max(1, Math.ceil(Math.sqrt(count)))
  const rows = Math.max(1, Math.ceil(count / columns))

  for (let index = 0; index < count; index += 1) {
    const row = Math.floor(index / columns)
    const column = index % columns
    const localEast = gridAxis(column, columns, xMin, xMax)
    const localNorth = gridAxis(row, rows, -35, 35)
    const localUp = type === 'UAV'
      ? 9 + (45 + (index % 4) * 8) / 4.4
      : 0

    poses.push({
      deviceCode: `${type}-${String(index + 1).padStart(3, '0')}`,
      deviceType: type,
      eastM: origin.eastM + localEast,
      northM: origin.northM + localNorth,
      upM: origin.upM + localUp,
      headingDeg: type === 'UAV' ? 90 : 0,
      speedMps,
      state: type === 'UAV' ? 'AIRBORNE' : 'SAILING',
      valid: true,
    })
  }
}

function createSeededRandom(seed: number | undefined) {
  let state = (Number.isFinite(seed) ? Math.trunc(seed as number) : 20260814) >>> 0
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0
    return state / 0x100000000
  }
}

interface PlanarPoint {
  eastM: number
  northM: number
}

function appendRandomStaging(
  poses: GridScenarioPose[],
  type: 'UAV' | 'USV',
  count: number,
  speedMps: number,
  origin: GridLayoutOptions['fleetOrigin'],
  random: () => number,
  occupied: PlanarPoint[],
  frontEastOffset: number,
  northBandOffset: number,
) {
  // Use the rendered surface-craft footprint for both types.  Sharing a
  // horizontal cell and relying on UAV altitude is physically valid, but in
  // the global top-down camera it looks exactly like a collision.
  const spacing = 14
  const columns = Math.max(1, Math.ceil(Math.sqrt(count)))
  const rows = Math.max(1, Math.ceil(count / columns))
  for (let index = 0; index < count; index += 1) {
    const row = Math.floor(index / columns)
    const column = index % columns
    // Seeded cell jitter preserves the requested random-looking idle layout
    // while the cell pitch guarantees visible clearance.
    const jitterEast = (random() - .5) * spacing * .18
    const jitterNorth = (random() - .5) * spacing * .18
    // Capture missions start as a pursuit, not as an almost-complete ring.
    // Keep the closest craft well behind the target and expand the staging
    // depth with fleet size. The target is placed symmetrically ahead of the
    // fleet below, so even 3+3 starts with more than 100 m of separation.
    const columnDirection = frontEastOffset >= 0 ? 1 : -1
    const eastM = origin.eastM + frontEastOffset + column * spacing * columnDirection + jitterEast
    const northM = origin.northM + northBandOffset
      + (row - (rows - 1) / 2) * spacing + jitterNorth
    occupied.push({ eastM, northM })

    poses.push({
      deviceCode: `${type}-${String(index + 1).padStart(3, '0')}`,
      deviceType: type,
      eastM,
      northM,
      upM: origin.upM + (type === 'UAV' ? 20 + (index % 4) * 2 : 0),
      headingDeg: random() * 360,
      speedMps,
      state: type === 'UAV' ? 'AIRBORNE' : 'SAILING',
      valid: true,
    })
  }
}

export function buildVirtualFleetGridLayout(
  options: GridLayoutOptions,
): GridScenarioPose[] {
  const poses: GridScenarioPose[] = []
  const captureMode = options.captureMode === true
  const uavCount = Math.max(1, Math.min(128, Math.trunc(options.uavCount)))
  const usvCount = Math.max(1, Math.min(128, Math.trunc(options.usvCount)))
  const captureColumns = Math.ceil(Math.sqrt(Math.max(uavCount, usvCount)))
  const captureCorridorHalfLength = 55 + Math.max(0, captureColumns - 2) * 4
  if (captureMode) {
    const random = createSeededRandom(options.seed)
    const occupied: PlanarPoint[] = []
    // Stage the friendly fleet east of the hostile target. The target's
    // initial escape therefore points west into the long open-water corridor,
    // rather than east toward Catalina and its bases.
    const stagingBandOffset = Math.min(62, 22 + Math.max(0, captureColumns - 2) * 5)
    appendRandomStaging(poses, 'UAV', uavCount, options.uavSpeedMps, options.fleetOrigin, random, occupied, captureCorridorHalfLength, stagingBandOffset)
    appendRandomStaging(poses, 'USV', usvCount, options.usvSpeedMps, options.fleetOrigin, random, occupied, captureCorridorHalfLength, -stagingBandOffset)
  } else {
    appendGrid(poses, 'UAV', uavCount, -50, 0, options.uavSpeedMps, options.fleetOrigin)
    appendGrid(poses, 'USV', usvCount, 0, 50, options.usvSpeedMps, options.fleetOrigin)
  }
  const plan = deriveAdaptiveScenarioPlan(uavCount, usvCount)
  const targetTypes = captureMode
    ? Array.from({ length: plan.threatCount }, () => 'CAPTURE_TARGET')
    : [
        ...Array.from({ length: plan.protectedCount }, () => 'ESCORT_TARGET'),
        ...Array.from({ length: plan.threatCount }, () => 'THREAT_TARGET'),
      ]
  targetTypes.forEach((targetType, index) => {
    const targetCode = captureMode
      ? `TARGET-${String(index + 1).padStart(3, '0')}`
      : index < plan.protectedCount
        ? `PROTECTED-${String(index + 1).padStart(3, '0')}`
        : `THREAT-${String(index - plan.protectedCount + 1).padStart(3, '0')}`
    const angle = 2 * Math.PI * index / Math.max(1, targetTypes.length)
    const radius = captureMode ? 0 : Math.min(plan.worldWidth, plan.worldHeight) * .34
    // Multi-target capture starts with every hostile clearly separated in
    // open water.  A single target remains on the corridor centreline.
    const captureSpread = Math.min(90, plan.worldHeight * .26)
    const captureTargetNorth = captureMode
      ? gridAxis(index, targetTypes.length, -captureSpread, captureSpread)
      : 0
    const captureTargetEast = captureMode
      ? -captureCorridorHalfLength - Math.abs(captureTargetNorth) * .12
      : 0
    poses.push({
      // Keep initial scene identity identical to the algorithm runtime frames.
      // Otherwise Unity creates TARGET-* objects during scene generation and
      // later rejects PROTECTED-* / THREAT-* updates as unknown devices.
      deviceCode: targetCode,
      deviceType: 'TARGET',
      targetType,
      eastM: options.fleetOrigin.eastM + captureTargetEast + Math.cos(angle) * radius,
      northM: options.fleetOrigin.northM + captureTargetNorth + Math.sin(angle) * radius,
      upM: options.fleetOrigin.upM,
      headingDeg: (angle * 180 / Math.PI + 180) % 360,
      speedMps: 0,
      state: targetType,
      valid: true,
    })
  })
  return poses
}
