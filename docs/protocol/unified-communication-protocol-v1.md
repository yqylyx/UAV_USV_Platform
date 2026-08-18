# UAV-USV 平台统一通信协议 v1.0

> 状态：开发组评审基线（Draft for Implementation）
> 日期：2026-08-08
> 适用：Vue、Spring Boot、ROS Gateway、ROS 2、Unity WebGL、真实 UAV/USV

## 1. 强制架构边界

1. 浏览器不得直连 ROS 或真实设备；所有控制命令经过后端鉴权、校验、记录和超时管理。
2. ROS 是任务与设备运行状态的权威来源；Unity 是仿真执行器或数字孪生展示端，不是业务真值来源。
3. 所有页面只消费后端同一条实时数据流。系统总览 Unity 与协同态势 2D 必须使用同一批 ROS 位姿。
4. 位姿、状态、检测结果走结构化实时消息；六路视频走 WebRTC，禁止把 Base64 JPEG 作为正式视频链路。
5. 仿真与真机使用同一套命令和遥测模型，只切换底层 Runtime Adapter。

```text
Vue ──REST控制──> Spring Boot ──v1控制报文──> ROS Gateway ──Action/Service──> ROS/设备
Vue <─WebSocket── Realtime Hub <──v1遥测报文── ROS Gateway <────Topic──────── ROS/设备
Vue <──────────────────────────── WebRTC Media Gateway <────相机流────────── ROS
```

## 2. 数据权威与用途

| 数据 | 权威来源 | 后端处理 | 页面用途 |
|---|---|---|---|
| 任务状态 | ROS 任务协调节点 | 校验、持久化、广播 | 所有页面统一显示 |
| 位姿 | ROS 定位/融合节点 | 去重、乱序检查、最新值缓存、批量入库 | Unity 与 2D 同帧展示 |
| 设备健康 | ROS 设备适配器 | 过期检测、告警 | 设备卡片、安全判断 |
| 视频 | ROS 相机/媒体网关 | WebRTC 会话管理 | 光电视觉 |
| 视觉检测 | ROS 识别节点 | 与视频帧序号对齐 | 检测框/目标列表 |
| 雷达 | ROS 雷达/融合节点 | 限频、二进制转发 | 雷达态势 |
| Unity ACK | Unity | 仅表示展示端已应用 | 诊断，不替代真机结果 |

## 3. 标识符

设备业务编号固定为：

```text
UAV-01 UAV-02 UAV-03
USV-01 USV-02 USV-03
TARGET-01 ESCORT-TARGET-01
```

ROS 命名空间：`/platform/fleet/uav_01`、`/platform/fleet/usv_01`。数据库主键、deviceCode 和硬件序列号必须分开。

```text
missionId: MISSION-20260808-001
runId:     RUN-20260808-001-01
commandId: CMD-20260808-000021
messageId: UUID/ULID
```

所有任务实时消息必须带 runId；接收方必须丢弃非当前 run 的帧。

## 4. 时间、坐标、单位

- 跨系统时间：带时区的 ISO-8601；延迟测量使用 `monotonicNs`。
- 全球坐标：WGS84；局部坐标：ENU，`X=East,Y=North,Z=Up`，单位米。
- 四元数顺序固定 `x,y,z,w`。
- Unity 适配层转换：`Unity(x,y,z)=ENU(east,up,north)`。
- 字段名必须带单位：`speedMps/headingDeg/altitudeMslM/latencyMs`。
- 禁止把 Unity X/Z 当作 ROS 或数据库真实坐标。

## 5. 统一消息信封

Gateway、后端和浏览器实时通道使用相同语义信封；JSON 统一 camelCase。ROS `.msg/.srv/.action` 使用 snake_case，由 Gateway 显式映射。

```json
{
  "specVersion": "1.0.0",
  "messageType": "telemetry.pose_batch",
  "messageId": "01J4S4TX0GJ7K2M2Q0R9A4N8FA",
  "timestamp": "2026-08-08T14:30:12.235+08:00",
  "monotonicNs": 827392183000,
  "sequence": 12851,
  "source": "ros-gateway-01",
  "missionId": "MISSION-20260808-001",
  "runId": "RUN-20260808-001-01",
  "deviceCode": null,
  "frameId": "map",
  "payload": {}
}
```

必填：`specVersion/messageType/messageId/timestamp/sequence/source/payload`。设备消息还必须提供 deviceCode；任务消息必须提供 runId。

## 6. 消息类型

| messageType | 方向 | 说明 |
|---|---|---|
| `gateway.hello` | 双向 | 版本与能力协商 |
| `gateway.heartbeat` | 双向 | 1 Hz 心跳 |
| `control.command` | 后端→ROS | 控制命令 |
| `control.ack` | ROS→后端 | 接受/拒绝 |
| `control.feedback` | ROS→后端 | 执行进度 |
| `control.result` | ROS→后端 | 最终结果 |
| `mission.status` | ROS→后端 | 任务权威状态 |
| `telemetry.pose_batch` | ROS→后端 | 同一采样时刻全编队位姿 |
| `telemetry.device_status` | ROS→后端 | 设备运行和健康状态 |
| `perception.visual_detections` | ROS→后端 | 视觉检测元数据 |
| `perception.radar_detections` | ROS→后端 | 雷达点迹/航迹 |
| `perception.pointcloud` | ROS→后端 | 二进制点云 |
| `media.stream_status` | ROS→后端 | WebRTC 流状态 |
| `system.error` | 双向 | 协议/系统错误 |

## 7. 控制流

### 7.1 命令枚举

```text
MISSION.START / PAUSE / RESUME / CANCEL / COMPLETE
UAV.TAKEOFF / HOVER / GOTO / RETURN_HOME / LAND / EMERGENCY_LAND
USV.DEPART / HOLD_POSITION / GOTO / RETURN_HOME / STOP_PROPULSION / EMERGENCY_STOP
```

禁止新增语义模糊的通用 `START/STOP/TAKEOFF/LAND`。

### 7.2 control.command

```json
{
  "specVersion": "1.0.0",
  "messageType": "control.command",
  "messageId": "01J4S5A7GE5G5TQ3STADNXQ4AD",
  "timestamp": "2026-08-08T14:30:12.235+08:00",
  "monotonicNs": 827392183000,
  "sequence": 91,
  "source": "platform-backend-01",
  "missionId": "MISSION-20260808-001",
  "runId": "RUN-20260808-001-01",
  "payload": {
    "commandId": "CMD-20260808-000021",
    "clientRequestId": "0191a176-8771-7bb1-a63c-acde48001122",
    "command": "MISSION.START",
    "priority": "NORMAL",
    "issuedBy": "admin",
    "deadlineAt": "2026-08-08T14:30:17.235+08:00",
    "target": {"scope": "MISSION", "deviceCodes": []},
    "parameters": {
      "algorithmCode": "GB_SFLA_CS",
      "algorithmVersion": "1.1.0",
      "runtimeMode": "SIMULATION",
      "targetCode": "TARGET-01",
      "minimumSeparationM": 15.0,
      "usvEncirclementRadiusM": 45.0,
      "uavFormationRadiusM": 75.0
    }
  }
}
```

`clientRequestId` 用于幂等；重复请求必须返回原 commandId，不能重复执行。

### 7.3 指令状态机

```text
CREATED → VALIDATING → DISPATCHED → ACCEPTED → EXECUTING → SUCCEEDED
                    ↘ REJECTED      ↘ FAILED / CANCELLED / TIMEOUT / EXPIRED
```

`ACCEPTED` 只表示 ROS 已接收；只有 `control.result=SUCCEEDED` 才表示实际完成。

```json
{"messageType":"control.ack","payload":{"commandId":"CMD-20260808-000021","status":"ACCEPTED","code":"COMMAND_ACCEPTED","message":"Mission accepted"}}
```

```json
{"messageType":"control.feedback","payload":{"commandId":"CMD-20260808-000021","status":"EXECUTING","progress":0.46,"phase":"FORMATION_CONVERGING","message":"6/6 vehicles participating"}}
```

```json
{"messageType":"control.result","payload":{"commandId":"CMD-20260808-000021","status":"SUCCEEDED","code":"ENCIRCLEMENT_ESTABLISHED","message":"Encirclement completed"}}
```

## 8. 信息流

### 8.1 telemetry.pose_batch

同一时刻尽量组成全编队批次，Unity 与 2D 使用同一个 sequence。

```json
{
  "messageType": "telemetry.pose_batch",
  "sequence": 12851,
  "missionId": "MISSION-20260808-001",
  "runId": "RUN-20260808-001-01",
  "frameId": "map",
  "payload": {
    "sampleTime": "2026-08-08T14:30:12.220+08:00",
    "vehicles": [{
      "deviceCode": "UAV-01",
      "localPosition": {"eastM": 35.26, "northM": -12.47, "upM": 30.0},
      "globalPosition": {"latitudeDeg": 22.856123, "longitudeDeg": 113.671234, "altitudeMslM": 52.3},
      "orientation": {"x": 0.0, "y": 0.0, "z": 0.3827, "w": 0.9239},
      "linearVelocityMps": {"x": 2.1, "y": 0.1, "z": 0.0},
      "headingDeg": 45.0,
      "positionValid": true
    }]
  }
}
```

### 8.2 telemetry.device_status

```json
{
  "messageType": "telemetry.device_status",
  "deviceCode": "USV-01",
  "payload": {
    "connectionState": "ONLINE",
    "operationState": "EXECUTING",
    "controlMode": "AUTONOMOUS",
    "armed": true,
    "batteryPercent": 82.0,
    "signalRssiDbm": -61.0,
    "speedMps": 4.2,
    "headingDeg": 135.0,
    "gpsFixType": 3,
    "satelliteCount": 18,
    "health": "NORMAL",
    "activeCommandId": "CMD-20260808-000021"
  }
}
```

### 8.3 视觉检测

视频走 WebRTC；检测框使用 0~1 归一化坐标，原点为左上角。

```json
{
  "messageType": "perception.visual_detections",
  "deviceCode": "UAV-01",
  "payload": {
    "cameraId": "CAM-UAV-01",
    "frameSequence": 18302,
    "imageWidth": 1920,
    "imageHeight": 1080,
    "detections": [{
      "trackId": "TARGET-01",
      "classification": "VESSEL",
      "confidence": 0.94,
      "box": {"x": 0.42, "y": 0.31, "width": 0.18, "height": 0.27}
    }]
  }
}
```

### 8.4 雷达检测

```json
{
  "messageType": "perception.radar_detections",
  "deviceCode": "USV-01",
  "payload": {
    "sensorId": "RADAR-USV-01",
    "scanId": 8912,
    "detections": [{
      "trackId": "TRACK-017",
      "rangeM": 184.5,
      "azimuthDeg": 32.6,
      "radialVelocityMps": -2.4,
      "confidence": 0.91,
      "classification": "VESSEL"
    }]
  }
}
```

## 9. ROS 2 接口

建立唯一接口包 `uav_usv_interfaces`。

| Topic | 类型 | 频率 | QoS |
|---|---|---:|---|
| `/platform/fleet/{id}/telemetry/pose` | `PoseWithCovarianceStamped` | UAV 30 Hz / USV 20 Hz | BestEffort KeepLast(5) |
| `/platform/fleet/{id}/telemetry/velocity` | `TwistWithCovarianceStamped` | 20 Hz | BestEffort KeepLast(5) |
| `/platform/fleet/{id}/status` | `VehicleStatus` | 2~5 Hz + 事件 | Reliable KeepLast(10) |
| `/platform/mission/status` | `MissionStatus` | 事件 + 1 Hz | Reliable TransientLocal |
| `/platform/fleet/{id}/visual/detections` | `VisualDetectionArray` | 5~15 Hz | BestEffort KeepLast(3) |
| `/platform/fleet/{id}/radar/detections` | `RadarDetectionArray` | 10~20 Hz | BestEffort KeepLast(5) |
| `/platform/fleet/{id}/lidar/points` | `PointCloud2` | 5~10 Hz | BestEffort KeepLast(2) |

长任务必须使用 Action：

```text
/platform/mission/execute                ExecuteMission.action
/platform/fleet/{id}/execute_command     ExecuteVehicleCommand.action
```

Service：

```text
/platform/control/acquire
/platform/control/release
/platform/fleet/{id}/emergency_stop
/platform/capabilities/query
```

急停走独立高优先级 Service，不能排在普通命令队列后。

## 10. ROS Gateway v1 线协议

```text
开发：ws://127.0.0.1:8765/uav_usv/v1
生产：wss://<gateway-host>/uav_usv/v1
```

旧 `/uav_usv` 仅迁移兼容，不再扩展。

连接后双方先发送：

```json
{
  "specVersion": "1.0.0",
  "messageType": "gateway.hello",
  "messageId": "01J4S6...",
  "timestamp": "2026-08-08T14:30:00.000+08:00",
  "sequence": 1,
  "source": "ros-gateway-01",
  "payload": {
    "instanceId": "ros-gateway-01",
    "supportedVersions": ["1.0.0"],
    "runtimeModes": ["SIMULATION", "REAL"],
    "capabilities": ["CONTROL", "POSE", "DEVICE_STATUS", "VISUAL_DETECTION", "RADAR", "POINTCLOUD", "WEBRTC"],
    "binaryTelemetry": true
  }
}
```

- 控制、状态、ACK、低频数据：UTF-8 JSON。
- 位姿批次、雷达批次、点云：生产优先 Protobuf 二进制。
- 禁止 Base64 封装高频二进制。
- 心跳 1 Hz；3 秒无心跳为 DEGRADED，5 秒为 OFFLINE。
- 重连退避 1/2/4/8 秒，上限 15 秒。
- 重连只同步最新任务和设备快照，不重放历史位姿。

## 11. 浏览器实时通道

后端提供单一入口：`wss://<backend>/api/v1/realtime`。

```json
{
  "action": "subscribe",
  "topics": ["mission", "fleet.pose", "fleet.status", "visual.detections", "radar.detections"],
  "runId": "RUN-20260808-001-01"
}
```

同一浏览器只维护一个连接。页面切换只能销毁本页渲染器，不能停止任务、清空全局状态或重建 ROS 会话。

## 12. 实时性与防卡顿

| 链路 | 目标 |
|---|---|
| ROS→Gateway 位姿 | UAV 30 Hz，USV 20 Hz |
| Gateway→后端位姿批次 | 20~30 Hz |
| 后端→Unity/2D | 20~30 Hz，端到端 P95 < 150 ms |
| 设备卡片 | 5 Hz |
| 视觉检测 | 5~15 Hz |
| 雷达点迹 | 10~20 Hz |
| 控制 ACK | P95 < 500 ms |

实现要求：

1. 实时队列只保留每个设备最新帧，禁止无限积压。
2. ROS 接收线程不得同步逐帧写数据库；轨迹批量落库。
3. 浏览器以 `requestAnimationFrame` 绘制，Pinia 不保存无限历史。
4. Unity 每个渲染帧最多应用一份最新 pose batch。
5. 展示可以两帧插值，算法和数据库仍使用原始数据。
6. 丢弃 runId 不符、sequence 倒退和超过最大时延的帧。
7. 慢客户端自动降频，不能反向阻塞 ROS 接收线程。

## 13. 控制安全

- 命令必须包含操作者、commandId、clientRequestId、deadline、priority。
- 优先级：`EMERGENCY > MANUAL > MISSION > AUTONOMOUS_HOLD`。
- 同一设备同一时刻只能有一个有效控制租约。
- 真机模式检查地理围栏、最大高度、最小安全距离和遥测新鲜度。
- 浏览器不得操作电机/舵机原始执行量。
- 生产使用 WSS 和服务身份认证；所有命令与结果进入审计日志。

## 14. 错误码

```text
PROTOCOL_UNSUPPORTED_VERSION
PROTOCOL_INVALID_MESSAGE
PROTOCOL_SEQUENCE_REWIND
CONTROL_PERMISSION_DENIED
CONTROL_LEASE_CONFLICT
CONTROL_COMMAND_EXPIRED
CONTROL_COMMAND_DUPLICATED
CONTROL_TARGET_OFFLINE
CONTROL_STATE_CONFLICT
MISSION_ALGORITHM_UNAVAILABLE
MISSION_DEVICE_NOT_READY
MISSION_TARGET_NOT_AVAILABLE
MISSION_EXECUTION_FAILED
TELEMETRY_STALE
TELEMETRY_INVALID_FRAME
SENSOR_STREAM_UNAVAILABLE
```

错误必须包含 `code/message/retryable/details`；程序不得依赖中文 message 判断逻辑。

## 15. 当前系统迁移映射

| 旧消息/机制 | v1 | 要求 |
|---|---|---|
| `pose_frame` | `telemetry.pose_batch` | 增加 runId、frameId、速度、有效性 |
| `camera_frame` Base64 | WebRTC + `media.stream_status` | 仅保留开发兼容开关 |
| `radar_frame` | `perception.radar_detections` | 固定字段和单位 |
| `pointcloud_frame` | `perception.pointcloud` | 二进制 |
| `command` | `control.command` | 增加 commandId、deadline、幂等键 |
| 数字 `command_ack` | ack/feedback/result | 使用完整字符串状态机 |
| SSE `runtime-change` | WebSocket 实时数据 | SSE 只保留低频通知 |

Gateway 可在迁移期读取旧报文，但后端必须立即转换为 v1；新代码不得扩展旧格式。

## 16. 开发组分工

### 前端组

- 单例 Realtime WebSocket + 统一 Pinia Store。
- 四个页面只消费统一 Store。
- runId/sequence 过滤、固定轨迹窗口、插值绘制。
- 视频使用 WebRTC，检测框按 frameSequence 对齐。

### 后端组

- v1 Gateway Client、消息校验、完整命令状态机。
- `/api/v1/realtime`、最新状态缓存、慢客户端降频。
- 幂等、deadline、控制租约、安全检查、审计。
- 高频轨迹批量入库。

### ROS/算法组

- 建立唯一 `uav_usv_interfaces` 包。
- 任务/设备长命令使用 Action，急停使用 Service。
- 统一 deviceCode、ENU、SI；反馈携带 commandId/runId。

### Unity 组

- 只消费统一 pose batch，不自行产生业务真值。
- 丢弃旧 run/sequence，每帧只应用最新数据。
- 坐标转换集中在 Unity Adapter。
- Unity ACK 与 ROS 执行结果严格分开。

### 感知/媒体组

- 六路视频 WebRTC、统一 cameraId。
- 视觉检测携带 frameSequence 和归一化框。
- 雷达固定字段/单位，点云二进制。

## 17. 验收标准

1. 系统总览一次启动，完整收到 ACCEPTED、EXECUTING、最终 result。
2. Unity 与 2D 对同一 sequence 的位置误差小于 0.1 m（坐标转换误差除外）。
3. 页面切换不重启任务、不重建 ROS 会话、不回放积压帧。
4. 3 UAV + 3 USV 连续运行 30 分钟，无持续内存增长和明显卡顿。
5. 六路视频稳定，720P/1080P 可切换，检测框与帧对齐。
6. 雷达刷新不阻塞位姿和 ACK。
7. ROS 断开、乱序、重复帧、旧 run、命令超时均有确定结果。
8. SIMULATION 与 REAL 使用相同前后端接口。

## 18. 版本规则

- SemVer：`MAJOR.MINOR.PATCH`。
- 增加可选字段为 MINOR；删除、改名或改变语义为 MAJOR。
- 接收方忽略未知可选字段，但不得忽略未知 messageType、command 或关键状态。
- 协议、ROS interface、后端 DTO、前端 TypeScript 类型必须在同一变更中更新。

## 19. 实现细节冻结（v1.0 补充）

### 19.1 sequence 的作用域

`sequence` 不采用 Gateway 全局递增。全局序号会让无关消息互相产生“缺帧”，也无法在 Gateway 重启后可靠判断顺序。

v1 规则：

- 实时消息必须增加 `streamId`。
- 顺序键固定为 `(source, streamId, sequence)`。
- `sequence` 在一个 streamId 内从 1 严格递增，不允许回退或复用。
- Gateway 进程重启、数据源重启或任务 run 切换时必须生成新 streamId。
- 网络重连但 Gateway 未重启时，保持原 streamId 和 sequence 继续递增。
- messageId 负责消息唯一性；sequence 只负责流内排序和丢帧检测。
- 可增加 `gatewaySequence` 作为诊断字段，但业务不得用它判断设备数据顺序。

推荐 streamId：

```text
pose-batch:{runId}:{gatewayBootId}
device-status:{deviceCode}:{deviceBootId}
visual:{cameraId}:{sensorBootId}
lidar:{sensorId}:{sensorBootId}
radar:{sensorId}:{sensorBootId}
mission:{runId}:{coordinatorBootId}
```

### 19.2 pose_batch 是最新状态快照

`telemetry.pose_batch` 采用 `LATEST_STATE` 快照，不宣称六台设备在同一物理时刻同步采样。Gateway 按固定频率读取每台设备最后一条状态，组成一批，同时保留各设备原始信息：

```json
{
  "streamId": "pose-batch:RUN-20260808-001-01:gw-73fb",
  "sequence": 12851,
  "messageType": "telemetry.pose_batch",
  "payload": {
    "snapshotMode": "LATEST_STATE",
    "snapshotTime": "2026-08-08T14:30:12.235+08:00",
    "complete": false,
    "expectedDeviceCodes": ["UAV-01", "UAV-02", "UAV-03", "USV-01", "USV-02", "USV-03"],
    "missingDeviceCodes": [],
    "staleDeviceCodes": ["USV-03"],
    "vehicles": [{
      "deviceCode": "USV-03",
      "sourceTimestamp": "2026-08-08T14:30:11.510+08:00",
      "sourceSequence": 7721,
      "ageMs": 725,
      "fresh": false,
      "positionValid": true,
      "localPosition": {"eastM": 18.2, "northM": 4.1, "upM": 0.0},
      "orientation": {"x": 0.0, "y": 0.0, "z": 0.1, "w": 0.995}
    }]
  }
}
```

- `snapshotTime` 是 Gateway 组批时间。
- `sourceTimestamp/sourceSequence` 是设备或 ROS 源节点的原始值，不得覆盖。
- `ageMs = snapshotTime - sourceTimestamp`。
- `complete=true` 仅当所有 expectedDeviceCodes 均存在且 fresh。
- 默认 `freshnessThresholdMs=500`，实际部署允许配置；超过阈值仍可携带最后状态，但必须 `fresh=false`。
- 从未收到状态的设备不伪造 pose，放入 missingDeviceCodes。
- 算法使用原始时间戳；Unity/2D 可以基于 snapshotTime 做显示插值。

### 19.3 控制消息必须使用完整信封

`control.ack`、`control.feedback`、`control.result` 均必须包含完整统一信封，不能只发送 payload。三者还必须满足：

- `correlationId = 原 control.command.messageId`。
- payload.commandId 与原命令一致。
- missionId/runId 原样返回。
- 各自位于独立有序 control stream 中。
- timestamp 表示该事件在 ROS 侧产生的时间。

### 19.4 LiDAR、Radar 与融合航迹分离

- `perception.radar_detections` 仅表示真正雷达数据，sourceMask 包含 `SOURCE_RADAR`。
- Mid360、LV-DOT 统一归入 LiDAR。
- LiDAR 目标检测使用 `perception.lidar_detections`，sourceMask 包含 `SOURCE_LIDAR`。
- LiDAR 原始点云使用 `perception.lidar_pointcloud`。
- 多传感器融合结果使用 `perception.fused_tracks`，sourceMask 可以同时包含 CAMERA/LIDAR/RADAR/AIS 多个位。
- 不定义 SOURCE_FUSED；多个来源位同时置 1 即表示融合。

sourceMask 固定为：

```text
SOURCE_CAMERA = 1   // 1 << 0
SOURCE_LIDAR  = 2   // 1 << 1
SOURCE_RADAR  = 4   // 1 << 2
SOURCE_AIS    = 8   // 1 << 3
SOURCE_GNSS   = 16  // 1 << 4
```

### 19.5 规范文件

- Gateway Protobuf：`uav_usv_gateway_v1.proto`。
- ROS 任务 Action：`ros2/uav_usv_interfaces/action/ExecuteMission.action`。
- ROS 设备 Action：`ros2/uav_usv_interfaces/action/ExecuteVehicleCommand.action`。
- ROS 配置消息：`ros2/uav_usv_interfaces/msg/MissionConfig.msg`。

## 20. 与当前前后端代码的落地映射

本节以当前仓库代码为基线，规定迁移位置，避免 ROS、后端和前端各自实现一套 v1。

### 20.1 当前链路的实际情况

当前后端已经具备以下基础：

- `RosPoseWebSocketClient` 连接旧 `/uav_usv`，读取 `pose_frame/camera_frame/radar_frame/pointcloud_frame/command_ack`。
- `RosWebSocketCommandDispatcher` 可以通过旧 WebSocket 发送 command。
- `ControlCommand` 已保存 commandKey、runId、deviceId、下发和确认时间。
- `RuntimeStateService` 已接收 RosPoseFrame 并更新运行状态。
- `RuntimeEventPublisher` 提供 SSE，但只发送 `runtime-change` 通知，前端收到后再延迟请求 REST。

当前前端已经具备：

- `runtimeControl.ts` 的命令下发与命令日志。
- `unityBridge.ts` 的 Unity outbox、commandKey 和 ACK 等待。
- `trajectory.ts` 的轨迹帧过滤和两个 runtimeScope 通道。
- `UnityWebglPanel.vue` 的 iframe postMessage、Unity Ready、poseFrameApplied 和视觉帧桥接。

这些基础可以保留，但当前实时数据权威关系必须调整：

```text
当前部分链路：Unity trajectoryFrame → trajectoryStore → 2D
v1 目标链路：ROS pose_batch → Backend RealtimeHub → realtimeStore
                                              ├→ trajectoryStore/2D
                                              └→ UnityWebglPanel/Unity
```

Unity 发出的 `trajectoryFrame` 在 v1 后只能作为仿真调试/对比数据，不能覆盖 ROS 权威位姿。

### 20.2 后端改造映射

#### RosPoseWebSocketClient

当前一个类同时负责连接、解析和业务分发，应拆分为：

```text
RosGatewayWebSocketClient   连接、hello、heartbeat、重连、文本/二进制帧
GatewayEnvelopeDecoder      v1 JSON/Protobuf 解码和 schema 校验
GatewaySequenceGuard        streamId + sequence 去重、乱序过滤
ControlMessageHandler       ack/feedback/result
TelemetryMessageHandler     pose_batch/device_status
PerceptionMessageHandler    visual/lidar/radar/fused tracks
RealtimeHub                 最新状态缓存和浏览器广播
```

旧 `RosPoseWebSocketClient` 在迁移期仅作为 Legacy Adapter，把旧消息立即转换为 v1 envelope。

#### RosPoseFrame / RuntimeStateService

当前 `RosPoseFrame.VehiclePoseData` 只有 id、position、orientation，而且 `RuntimeStateService` 把同一个 batch sequence 和本机 now 用到所有设备，会丢失各设备原始采样时间。

v1 必须新增并保留：

```text
streamId
batchSequence
snapshotTime
deviceCode
sourceTimestamp
sourceSequence
ageMs
fresh
positionValid
velocity
frameId
```

RuntimeStateService 只负责业务状态聚合；高频帧缓存和广播移至 RealtimeHub，避免每帧触发数据库和 SSE 刷新。

#### ControlCommand / CommandStatus

当前 `ControlCommand.acknowledge()` 会同时设置 acknowledgedAt 和 completedAt，等于把“ROS 已接收”当作“动作已完成”。v1 必须改成独立方法：

```text
accept()     → ACCEPTED，只设置 acceptedAt
execute()    → EXECUTING，记录 startedAt/phase/progress
succeed()    → SUCCEEDED，设置 completedAt
reject()     → REJECTED
fail()       → FAILED
cancel()     → CANCELLED
expire()     → EXPIRED
timeout()    → TIMEOUT
```

数据库需要新迁移增加：`client_request_id/mission_id/accepted_at/started_at/deadline_at/progress/phase/result_code/priority/correlation_id`。不得修改已经执行的旧 Flyway 文件。

#### RosCommandAckListener

当前把数字状态 1/3 映射为成功确认、4/5/6 映射为失败。迁移后分别处理：

```text
control.ack      → accept/reject
control.feedback → execute + progress/phase
control.result   → succeed/fail/cancel/timeout/expire
```

旧数字映射只存在于 Legacy Adapter。

#### RuntimeEventPublisher / Monitoring Store

当前 SSE 只发变更通知，前端等待约 1 秒后重新请求 summary/nodes，适合低频节点状态，不适合位姿和感知。

- SSE 保留：系统告警、节点上下线等低频事件。
- 新建 `/api/v1/realtime` WebSocket：pose/status/mission/detections。
- REST 保留：首屏快照、历史查询、断线恢复。
- WebSocket 连接成功后先发送 snapshot，再发送增量流。

### 20.3 前端改造映射

#### 新增 realtimeStore

新增全局单例 store，不按页面建立连接：

```text
stores/realtime.ts
  connectionState
  currentRunId
  streamSequences: Map<streamId, sequence>
  latestPoseBatch
  deviceStatusByCode
  missionStatus
  visualDetectionsByCamera
  lidarDetectionsBySensor
  radarDetectionsBySensor
  fusedTracks
```

App 登录成功后连接，退出登录后断开；路由切换不能断开。

#### trajectoryStore

当前 `trajectory.ts` 只用单个 lastSequence，并允许 1~3 的小序号自动判断重启。v1 改为：

- 使用 `streamId + sequence`，streamId 变化才重置流。
- 必须校验 runId。
- agents 增加 sourceTimestamp/sourceSequence/ageMs/fresh。
- 坐标系统固定为 ROS_ENU，二维组件负责 ENU→屏幕坐标。
- 不再接受 Unity trajectoryFrame 作为权威数据。

#### DashboardView

当前页面存在本地 `poseFrameSequence++`，它只能代表浏览器发送次数，不能代表 ROS 数据顺序。v1 必须删除该权威语义：

- 给 Unity 的 sequence 原样使用 ROS pose_batch.sequence。
- 同时传 streamId、runId、snapshotTime 和每设备 sourceTimestamp。
- 页面启动任务只调用后端；不得同时直接启动一套独立 Unity 任务状态机。

#### UnityWebglPanel / unityBridge

现有 iframe postMessage 和 outbox 可以保留，但职责收窄：

- 输入：`applyPoseBatch/setMissionState/selectDevice/setCameraMode/setTrajectoryVisible`。
- `poseFrame` 更新为 `applyPoseBatch`，队列始终覆盖旧帧，只保留最新帧。
- `poseFrameApplied` 只用于 Unity 渲染诊断，不回写 ROS 命令成功。
- `commandAck` 只确认 Unity 展示/仿真接口，不替代 control.result。
- Unity 的 `trajectoryFrame` 只在 LEGACY_SIMULATION 模式允许进入对比通道。

#### visualSensorStore

当前 Unity JPEG/后端 Blob 轮询保留为开发兼容模式。正式模式改为：

- WebRTC MediaStream 存放视频。
- realtimeStore 存放 visual detections。
- cameraId + frameSequence 对齐视频与检测框。
- 页面销毁 video renderer 时不得销毁全局任务和遥测连接。

### 20.4 系统总览启动的代码级闭环

```text
DashboardView
  POST /api/v1/mission-runs (clientRequestId)
    → RuntimeControlService 校验并保存 ControlCommand
    → RosGatewayWebSocketClient 发送 control.command
    ← control.ack ACCEPTED
    ← control.feedback EXECUTING
    ← telemetry.pose_batch 20~30 Hz
       → RealtimeHub
       → /api/v1/realtime
       → realtimeStore.ingestPoseBatch()
          ├→ trajectoryStore（协同态势 2D）
          └→ unityBridge.sendFor(applyPoseBatch)（系统总览 Unity）
    ← visual/lidar/radar/fused detections
       → 对应感知页面
    ← control.result
       → ControlCommand 最终状态 + 所有页面同步
```

### 20.5 分阶段兼容开关

建议配置：

```yaml
app:
  runtime:
    ros-gateway-protocol: v1
    legacy-gateway-enabled: true
  realtime:
    websocket-enabled: true
    pose-publish-hz: 25
  media:
    transport: webrtc
```

迁移顺序：先让 Gateway 双发旧/v1，后端切到 v1，前端切到 Realtime Store，最后关闭旧 pose_frame、Unity trajectoryFrame 权威入口和 Base64 视频。
