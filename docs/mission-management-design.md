# 任务管理模块设计草案

## 模块目标

任务管理模块是后续通信监控、围捕展示、实验评估与回放的业务入口。

当前阶段先完成可配置、可查询、可展示的任务管理闭环，不直接强依赖 ROS/Unity 完整控制能力。

## 任务类型

建议初始支持：

- `TARGET_INSPECTION`：目标巡检
- `COOPERATIVE_ENCIRCLEMENT`：协同围捕
- `PATH_TRACKING`：路径跟踪
- `COMMUNICATION_RELAY`：区域中继
- `CUSTOM`：自定义任务

界面展示可使用中文：

- 目标巡检
- 协同围捕
- 路径跟踪
- 区域中继
- 自定义任务

## 任务状态

建议状态：

- `DRAFT`：草稿
- `READY`：待执行
- `RUNNING`：运行中
- `PAUSED`：暂停
- `COMPLETED`：已完成
- `FAILED`：异常
- `CANCELLED`：已取消

## 任务阶段

围捕任务建议阶段：

- `PREPARE`：任务准备
- `TARGET_DETECTED`：目标发现
- `ASSIGNMENT`：协同分配
- `TRACKING`：路径跟踪
- `ENCIRCLEMENT`：围捕收缩
- `CAPTURED`：完成围捕
- `EVALUATION`：结果评估

## 数据库建议

### mission_task

任务主表。

字段建议：

- `id`
- `code`
- `name`
- `type`
- `status`
- `stage`
- `description`
- `target_name`
- `target_behavior`
- `area_name`
- `created_by`
- `planned_start_time`
- `started_at`
- `finished_at`
- `created_at`
- `updated_at`

### mission_task_device

任务与设备绑定表。

字段建议：

- `id`
- `task_id`
- `device_id`
- `role`
- `sort_order`
- `created_at`

角色建议：

- `LEADER`
- `UAV_RECON`
- `UAV_TRACK`
- `USV_INTERCEPT`
- `USV_BLOCKADE`
- `ROS_BRIDGE`
- `UNITY_CLIENT`

### mission_task_parameter

任务参数表。

字段建议：

- `id`
- `task_id`
- `param_group`
- `param_key`
- `param_value`
- `value_type`
- `created_at`
- `updated_at`

参数分组建议：

- `ENVIRONMENT`
- `COMMUNICATION`
- `SENSOR`
- `TARGET`
- `CONTROL`

### mission_event

任务事件日志。

字段建议：

- `id`
- `task_id`
- `level`
- `event_type`
- `title`
- `content`
- `source`
- `event_time`
- `created_at`

### mission_trajectory_point

轨迹点表。

字段建议：

- `id`
- `task_id`
- `device_id`
- `source`
- `x`
- `y`
- `z`
- `heading`
- `speed`
- `recorded_at`

### mission_evaluation

任务评估结果表。

字段建议：

- `id`
- `task_id`
- `completion_time_seconds`
- `capture_rate`
- `communication_cost`
- `path_length`
- `energy_cost`
- `cooperation_score`
- `summary`
- `created_at`

## 后端接口建议

### 任务 CRUD

- `GET /api/missions`
- `GET /api/missions/{id}`
- `POST /api/missions`
- `PUT /api/missions/{id}`
- `DELETE /api/missions/{id}`

### 任务状态

- `POST /api/missions/{id}/prepare`
- `POST /api/missions/{id}/start`
- `POST /api/missions/{id}/pause`
- `POST /api/missions/{id}/complete`
- `POST /api/missions/{id}/cancel`

当前阶段可以只实现状态流转，不直接启动 ROS/Unity。

### 任务事件

- `GET /api/missions/{id}/events`
- `POST /api/missions/{id}/events`

### 任务轨迹

- `GET /api/missions/{id}/trajectory`
- `POST /api/missions/{id}/trajectory`

后续 ROS 位姿可按任务写入轨迹点。

### 任务评估

- `GET /api/missions/{id}/evaluation`
- `POST /api/missions/{id}/evaluation`

## 前端页面建议

### 任务列表

展示：

- 任务名称
- 任务类型
- 当前状态
- 当前阶段
- 绑定 UAV/USV 数量
- 创建时间
- 操作入口

### 新建任务

采用分步式配置：

1. 任务类型
2. 智能体选择
3. 目标参数
4. 通信参数
5. 环境参数
6. 保存配置

### 任务详情

展示：

- 任务基础信息
- 参与设备
- 当前阶段
- 事件时间线
- 轨迹/围捕概览
- 运行控制入口

## 与 ROS/Unity 的关系

当前阶段：

- 任务只在平台内创建和管理。
- 任务状态变化不直接控制 ROS/Unity。
- 可以用模拟事件和轨迹填充页面。

后续阶段：

- 任务启动时生成控制命令。
- 后端调用 WSL 脚本或 ROS/Unity 适配接口。
- ROS/Unity 上报任务事件、位姿和状态。
- 平台根据任务 ID 归档轨迹和评估结果。

## 实施建议

第一轮只做：

- 任务主表
- 任务设备绑定表
- 任务参数表
- 任务列表
- 新建任务
- 任务详情

第二轮再做：

- 任务事件
- 阶段时间线
- 模拟围捕轨迹

第三轮再做：

- ROS/Unity 任务绑定
- 真实轨迹归档
- 评估回放
