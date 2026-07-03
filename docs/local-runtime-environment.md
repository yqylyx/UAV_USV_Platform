# 本机联调环境与配置说明

本文档记录当前开发机的 UAV-USV 平台联调环境，并说明其他同学拉取代码后需要改哪些本地配置。

> 注意：仓库不提交真实密码、服务器登录密码和个人本地配置。请复制 `backend/src/main/resources/application-local.example.yml` 为 `application-local.yml` 后在本机填写。

## 当前开发机环境

| 项目 | 当前值 |
| --- | --- |
| Windows | Windows 10 专业版 10.0.19045，64 位 |
| Java | Oracle JDK 17，路径 `D:\java17` |
| Maven | Maven Wrapper，Apache Maven 3.9.11 |
| Node.js | v20.20.2 |
| npm | 10.8.2 |
| MySQL 客户端 | MySQL 8.0.45 |
| WSL 发行版 | `Ubuntu22`，WSL2 |
| Unity Editor | `F:\Unity\Editors\2022.3.57f1\Editor\Unity.exe` |
| Unity 项目 | `F:\Unity\Projects\unity_ws` |
| 平台仓库 | `F:\UAV_USV_Platform` |
| 平台运行脚本 | `F:\UAV_USV_Platform\scripts\uav-usv-runtime.sh` |

## WSL 内 ROS / UAV 项目要求

运行监控页的“运行 / 停止”不是普通前端按钮，它会通过 Spring Boot 调用 Windows `wsl.exe`，再进入 WSL 启动 ROS2、Gazebo、WebSocket bridge 和 Unity 联调。

当前脚本默认要求 WSL 内存在：

```bash
/opt/ros/humble/setup.bash
~/UAV_USV
~/UAV_USV/install/setup.bash
~/ros_tcp_ws
~/PX4-Autopilot
```

当前运行脚本会启动：

```bash
ros2 launch uav_usv_sim uav_usv_cooperation_demo.launch.py land_on_deck:=false px4_dir:=$HOME/PX4-Autopilot
ros2 launch uav_usv_sim uav_usv_unity_websocket_bridge.launch.py
```

因此，其他电脑如果 WSL 用户名、UAV 项目路径、PX4 路径或 ROS workspace 名称不同，需要先改脚本或提供对应环境变量。

## 本地配置文件

首次拉取后执行：

```powershell
Copy-Item backend/src/main/resources/application-local.example.yml backend/src/main/resources/application-local.yml
```

然后按自己的电脑修改 `application-local.yml`。

关键配置项：

```yaml
spring:
  datasource:
    url: jdbc:mysql://你的数据库地址:3306/uav_usv_platform?useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai&useSSL=false&allowPublicKeyRetrieval=true
    username: 你的数据库用户
    password: 你的数据库密码

app:
  integration:
    token: 本机联调token
  security:
    bootstrap-admin:
      username: admin
      password: 123456
  control:
    wsl-distribution: Ubuntu22
    ros-script: F:/UAV_USV_Platform/scripts/uav-usv-runtime.sh
    unity-editor: F:/Unity/Editors/2022.3.57f1/Editor/Unity.exe
    unity-project: F:/Unity/Projects/unity_ws
  runtime:
    ros-websocket-url: ws://127.0.0.1:8765/uav_usv
```

## 启动方式

根目录启动前后端：

```powershell
npm run dev
```

分别启动：

```powershell
npm run dev:backend
npm run dev:frontend
```

默认访问：

```text
前端：http://127.0.0.1:5174
后端：http://127.0.0.1:8081
登录：admin / 123456
```

## 运行 / 停止功能依赖

运行监控页点击“运行”时，后端会：

1. 检查当前是否已有活动会话。
2. 调用 `wsl.exe -d <wsl-distribution> -- bash <ros-script> start`。
3. 在 Unity 项目的 `Library/PlatformControl` 下写入 `start.request`。
4. 如果 Unity 未打开，尝试通过 `unity-editor` + `unity-project` 打开 Unity。
5. 等待 ROS WebSocket 和 Unity heartbeat 回传。

点击“停止”时，后端会：

1. 在 Unity 项目的 `Library/PlatformControl` 下写入 `stop.request`。
2. 调用 `wsl.exe -d <wsl-distribution> -- bash <ros-script> stop`。
3. 将 ROS、Unity、UAV、USV 节点标记为下线。

## 其他电脑常见问题

| 现象 | 常见原因 | 处理 |
| --- | --- | --- |
| 登录成功但运行按钮无效 | 后端未启动或 CSRF/session 失效 | 重新启动后端并刷新页面 |
| 运行后提示 ROS 脚本不存在 | `ros-script` 仍是开发机路径 | 修改 `application-local.yml` |
| 运行后提示找不到 WSL 发行版 | 本机 WSL 名称不是 `Ubuntu22` | `wsl -l -v` 查看后修改 `wsl-distribution` |
| ROS 启动失败 | WSL 内没有 `~/UAV_USV/install/setup.bash` | 进入 WSL 编译 UAV 项目 |
| Unity 启动失败 | Unity Editor 或 Unity 项目路径不同 | 修改 `unity-editor`、`unity-project` |
| 页面显示 Unity 离线 | WebGL 页面未打开或 Unity heartbeat 未发送 | 打开系统总览 WebGL 页面或 Unity 场景 |

## 提交规范提醒

- 不提交 `backend/src/main/resources/application-local.yml`。
- 不提交数据库密码、服务器密码、个人绝对路径到代码逻辑中。
- 本地路径只放在 `application-local.example.yml` 或文档里作为示例。
- 后续建议新增“运行环境自检接口”，在点击运行前提示 WSL、ROS、Unity 哪一项未配置。
