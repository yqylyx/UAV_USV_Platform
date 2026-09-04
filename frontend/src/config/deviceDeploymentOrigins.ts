/**
 * Visualization-only deployment anchors.
 *
 * Temporary compatibility for ArduPilot local ENU -> Unity shared display map ENU.
 * These values are not Gazebo/ROS runtime map truth.
 * Remove this mapping after Gateway provides mapPositionEnuM.
 * UAV source: src/uav_usv_bringup/launch/fleet_dynamic_capture.launch.py (UAV_CONFIG).
 * USV source: src/uav_usv_gazebo/worlds/heterogeneous_332.sdf (initial <pose>).
 */
export const deviceDeploymentOrigins = {
  uav_01: { east: -86.86, north: -222.43, up: 19.75 },
  uav_02: { east: -75.00, north: -215.00, up: 19.75 },
  uav_03: { east: -63.14, north: -207.57, up: 19.75 },
  usv_01: { east: -120.00, north: -305.00, up: 0.00 },
  usv_02: { east: -75.00, north: -320.00, up: 0.00 },
  usv_03: { east: -30.00, north: -305.00, up: 0.00 },
} as const
