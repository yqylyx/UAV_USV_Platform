# Unity–平台兼容层

当前平台 WebGL 基线对应 Unity 提交：

- Unity commit：`f24959c32b072cc7f18ff815f6ab22a580fc531b`
- 平台桥版本：`unity-f24959c-platform-v2`
- 设备：3 UAV、3 USV
- 任务对象：`friendly_ship`、`enemy_ship`

## 边界

平台不得修改 Unity 地形、仿真流程或算法业务代码。所有前后端适配代码统一维护在：

```text
unity-tools/Assets/Scripts/UavUsv/PlatformTools/
```

更新 Unity 后，将该目录覆盖到隔离构建副本的：

```text
Assets/Scripts/UavUsv/PlatformTools/
```

再执行 `UavUsv.Editor.Tools.VueWebGlBuildTool.Build`。不要在未经验证时直接覆盖正式 Unity 项目。

## WebGL 能力握手

`UnityPlatformCompatibilityBridge` 在场景与各工具桥就绪后发送：

```text
platformBridgeReady
```

能力列表包括：

- `camera-control`
- `vehicle-control`
- `trajectory-telemetry`
- `local-capture-scenario`
- `algorithm-scenario`
- `visual-sensor`
- `gazebo-comparison`

Vue 只有收到完整就绪消息后才清空指令队列。Unity 画面加载成功不等于控制桥已经可用。

## 运行域

- `SYSTEM_OVERVIEW`：系统总览、设备观察、内置简单任务和 Unity 视觉传感器。
- `MISSION_CENTER`：任务中心独立算法运行，2D 与 3D 使用同一个运行批次。

两个运行域可复用同一套 WebGL 构建文件，但必须使用不同 iframe 与运行实例标识，不能共享任务状态。

## 相机协调

新版 Unity 默认启用 `GazeboComparisonCamera`。平台发出设备选择、网页相机切换、算法场景加载或算法位姿帧时，兼容桥会关闭固定 Gazebo 相机，避免其在 `LateUpdate` 中覆盖网页相机。切换到 `gazebo-comparison` 模式时可恢复该视角。

新版 `SimulationBootstrap` 只创建 Gazebo 场景，不再挂载本地围捕组件。`UnityScenarioCompatibilityInstaller` 会在运行时绑定现有三机三艇、目标船、停机坪和岸基节点，并让本地场景保持未启动状态，直到平台发送 `missionStart`。任务中心算法坐标保持局部坐标，3D 展示时只平移到 Gazebo 安全任务海域，2D 数据不改写。

## 更新后的最低验收

1. 六台设备均可选择，`uav_01/usv_01` 与 `UAV-01/USV-01` 均能识别。
2. 系统总览与任务中心运行域互不串联。
3. 围捕、护航的算法帧能同时驱动任务中心 2D 和 3D。
4. 六路视觉画面直接来自 Unity，无需等待 ROS 摄像头。
5. 隐藏/显示轨迹必须收到 Unity 的 `trajectoryVisibilityChanged` 确认。
6. 前端、后端和 Unity WebGL 构建全部通过后才可同步至正式项目。
