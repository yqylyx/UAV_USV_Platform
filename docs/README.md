# 项目说明文档索引

本目录用于记录 UAV-USV 海空协同仿真与任务控制平台的开发约定、模块边界和后续迭代方向。

## 文档列表

- [architecture.md](architecture.md)：对齐 PPT 的五层软件架构，说明当前项目在 Spring Boot、Vue、ROS2/Gazebo、Unity3D 和算法服务中的定位。
- [frontend-backend-roadmap.md](frontend-backend-roadmap.md)：梳理前后端已有模块、下一阶段模块和接口开发顺序。
- [mission-management-design.md](mission-management-design.md)：任务管理 / 任务配置模块的数据库、后端、前端和接口设计草案。

## 维护原则

- 先写清楚模块边界，再写代码。
- 前端页面必须围绕业务闭环，不做只有静态装饰的大屏。
- 后端模块保持企业级 MVC 分层结构。
- ROS/Unity 接入先做只读监控和状态回传，再逐步做控制命令。
- 危险的启动/停止/进程控制必须有明确状态判断和人工确认。
