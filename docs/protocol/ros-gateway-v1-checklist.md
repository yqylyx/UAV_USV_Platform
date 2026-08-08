# ROS Gateway v1 开发联调清单

主协议：`unified-communication-protocol-v1.md`。

## P0：先形成控制与位姿闭环

- [ ] 冻结 deviceCode、missionId、runId、commandId。
- [ ] 冻结 ENU/WGS84/Unity 映射和所有单位。
- [ ] 新增 `/uav_usv/v1` 和 `gateway.hello`。
- [ ] 实现 1 Hz heartbeat 与 3/5 秒状态判断。
- [ ] 实现 control.command/ack/feedback/result。
- [ ] 实现 mission.status。
- [ ] 实现 telemetry.pose_batch 与 runId/sequence 校验。
- [ ] 后端扩展状态机，不再把 ACK 当完成。
- [ ] 前端单一 Realtime Store，Unity 与 2D 使用同一批次。

## P1：感知和性能

- [ ] telemetry.device_status。
- [ ] perception.visual_detections。
- [ ] perception.radar_detections。
- [ ] 六路相机迁移 WebRTC。
- [ ] 点云二进制化。
- [ ] 高频轨迹批量落库。
- [ ] 最新帧覆盖、慢客户端降频。

## P2：真机前置安全

- [ ] 控制租约和优先级仲裁。
- [ ] commandId 幂等、deadline。
- [ ] 围栏、高度、最小距离、遥测过期检查。
- [ ] 独立急停通道。
- [ ] WSS 与服务认证。
- [ ] 完整审计日志。
- [ ] SITL、HIL、单机真机、六机协同测试。

## 联调必须保留的样本

1. gateway.hello。
2. 一次完整任务的 command/ack/feedback/result。
3. 连续 10 秒 pose batch。
4. 一帧设备状态。
5. 一帧视觉检测及对应 frameSequence。
6. 一帧雷达检测。
7. ROS 断开与重连过程。
8. 旧 run、乱序 sequence、重复 commandId 的拒绝结果。
