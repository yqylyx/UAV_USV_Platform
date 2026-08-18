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

export function buildVirtualFleetGridLayout(
  options: GridLayoutOptions,
): GridScenarioPose[] {
  const poses: GridScenarioPose[] = []
  appendGrid(
    poses,
    'UAV',
    Math.max(1, Math.min(100, Math.trunc(options.uavCount))),
    -50,
    0,
    options.uavSpeedMps,
    options.fleetOrigin,
  )
  appendGrid(
    poses,
    'USV',
    Math.max(1, Math.min(100, Math.trunc(options.usvCount))),
    0,
    50,
    options.usvSpeedMps,
    options.fleetOrigin,
  )
  poses.push({
    deviceCode: 'TARGET-001',
    deviceType: 'TARGET',
    // The single rendered target is the escort threat. Keep it outside the
    // fleet ring so Unity and the escort adapter share the same initial pose.
    eastM: options.fleetOrigin.eastM + 55,
    northM: options.fleetOrigin.northM,
    upM: options.fleetOrigin.upM,
    headingDeg: 0,
    speedMps: 0,
    state: 'THREAT_TARGET',
    valid: true,
  })
  return poses
}
