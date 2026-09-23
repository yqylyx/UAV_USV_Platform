import { describe, expect, it } from 'vitest'
import { adaptVirtualAlgorithmFrame } from '../virtualAlgorithmFrameAdapter'
import type { AlgorithmRuntimeFrame } from '@/types/mission'
const frame = (coordinateFrame: 'FLEET_LOCAL_ENU' | 'GLOBAL_ENU') => ({
  runId: 991001, sequence: 12, timestamp: 1000, coordinateFrame,
  agents: [{ code: 'UAV-001', type: 'UAV', x: 10, y: 20, z: 25, heading: 90, status: 'ACTIVE' },
    { code: 'USV-001', type: 'USV', x: -2, y: 3, z: 0, heading: 180, status: 'ACTIVE' }],
  targets: [{ code: 'PROTECTED-001', type: 'ESCORT_TARGET', x: 1, y: 2, z: 0, heading: 0, visible: true },
    { code: 'THREAT-001', type: 'THREAT_TARGET', x: 5, y: 6, z: 0, heading: 270, visible: true }],
} as AlgorithmRuntimeFrame)
describe('original algorithm pose compatibility', () => {
  it('converts local ENU once and preserves run, frame and all target identities', () => {
    const input=frame('FLEET_LOCAL_ENU')
    const origin={ eastM: -360, northM: -285, upM: 0 }
    const first=adaptVirtualAlgorithmFrame(input,new Map(),{fleetOrigin:origin})
    expect(first.payload).toMatchObject({runId:991001,sequence:12,sampleTime:1000,coordinateFrame:'GLOBAL_ENU'})
    expect(first.payload.vehicles[0]).toMatchObject({deviceCode:'UAV-001',eastM:-350,northM:-265,upM:25,headingDeg:90})
    expect(first.payload.targets.map(x=>x.deviceCode)).toEqual(['PROTECTED-001','THREAT-001'])
    const replay=adaptVirtualAlgorithmFrame(input,first.nextState,{fleetOrigin:origin})
    expect(replay.payload).toEqual(first.payload)
    expect(input.agents[0]?.x).toBe(10)
  })
  it('does not add fleet origin to already global coordinates', () => {
    const result=adaptVirtualAlgorithmFrame(frame('GLOBAL_ENU'),new Map(),{fleetOrigin:{eastM:-360,northM:-285,upM:2}})
    expect(result.payload.vehicles[0]).toMatchObject({eastM:10,northM:20,upM:25,headingDeg:90})
    expect(result.payload.vehicles[1]).toMatchObject({eastM:-2,northM:3,upM:0,headingDeg:180})
  })
})
