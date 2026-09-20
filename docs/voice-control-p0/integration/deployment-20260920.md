# 本机隔离环境部署记录 — 2026-09-20

- 后端业务基线：760075d，包含 prepare 元数据与持久化画面期限。
- 前端快照：nly/p0-frontend-20260920 / f5a3dcd，包含 11a06f1 展示状态轮询与重新同步修复。
- 前端：http://127.0.0.1:15174；后端：http://127.0.0.1:18081。
- 独立库：uav_usv_p0_integration；数据库账号 p0_integration，仅限该库；网页账号 p0_admin / ADMIN。
- 密码不在仓库中：本机桌面“UAV-USV-P0隔离环境账号-仅本机.md”保存网页登录信息，完整本机启动凭据位于忽略目录 .local-tools/p0-integration/credentials.json。
- P0、Mock、Unity 展示 v1 开关保持关闭；ROS/Gateway/视觉传感器连接关闭。

## 实际验证

最新后端打包成功；空库 Flyway V1—V19 迁移及 JPA 启动成功；health=UP；通过前端代理登录 p0_admin 成功，/api/auth/me 确认 ADMIN，/api/voice/contexts 返回 200 和空列表；携带有效 CSRF 与幂等键的新增提案请求返回 503 VOICE_CONTROL_DISABLED。

专用数据库账号能访问联调库，访问原开发库被拒绝。没有运行算法进程，没有验证 WebGL 或真实 v1 端到端。

## 运行与重启

两个服务在本机后台运行，进程 PID 与代码版本记录于 .local-tools/p0-integration/runtime.json；日志在同目录 backend.out.log/backend.err.log/frontend.out.log/frontend.err.log。停止时核对 PID/命令行仅终止本次实例，不杀全部 Java/Node/Python。环境没有配置开机自启。

前端为独立源码快照，node_modules 复用本机已安装依赖；没有切换或合并当前工作区。后续前端新提交须重新准备快照，本机快照不会自动更新。重启方式见 README 启动脚本；前端脚本默认启动当前仓库前端，使用前必须先准备好希望联调的代码版本，不能误以为它自动选择上述快照。

本地址只可在此电脑访问。四位同学各自在自己机器部署，或另行准备受控共享环境；不能把 127.0.0.1 当作跨机器访问地址。使用独立浏览器配置避免不同端口间 CSRF Cookie 冲突。

真实 runner v1 与 Unity 就绪后才启用控制并重新 prepare。数据库、测试账号和后台进程属于本机资源，上传 GitHub 的只有模板和说明，不会给其他同学自动创建环境。
