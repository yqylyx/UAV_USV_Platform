# 视觉传感器接入

视觉感知中心使用独立图像链路，不占用任务位姿和控制桥的 `8765` 端口：

`Gazebo 相机 → ROS 2 CompressedImage → visual_sensor_websocket_bridge.py:8766 → Spring 缓存 → Vue`

默认通道与设备一一对应：

- `uav_01`、`uav_02`、`uav_03`：无人机垂直下视相机；
- `usv_01`、`usv_02`、`usv_03`：无人艇艇艏前视相机。

桥接器默认订阅 `/uav_usv/<device>/camera/image/compressed`。如果 Gazebo 实际话题不同，
请通过 ROS 参数 `camera_ids` 和 `camera_topics` 传入两个等长数组；前端不会伪造离线画面。

## ROS 2 启动

将 `visual_sensor_websocket_bridge.py` 安装为 `uav_usv_sim` 可执行程序后运行：

```bash
source /opt/ros/humble/setup.bash
source ~/uav_usv_ws/install/setup.bash
ros2 launch uav_usv_sim uav_usv_visual_sensor_bridge.launch.py
```

如需修改监听地址或端口：

```bash
ros2 launch uav_usv_sim uav_usv_visual_sensor_bridge.launch.py \
  ws_host:=0.0.0.0 ws_port:=8766
```

Spring 后端默认连接 `ws://127.0.0.1:8766/visual_sensors`，可用环境变量
`VISUAL_SENSOR_WEBSOCKET_URL` 覆盖。

六路总览请求约 2 FPS 缩略帧，单路聚焦请求约 12 FPS 当前相机，从而限制网络、浏览器解码和
WebGL 并行运行时的负载。页面只显示真实收到的 JPEG；未收到、超时和网关离线均有明确状态。
