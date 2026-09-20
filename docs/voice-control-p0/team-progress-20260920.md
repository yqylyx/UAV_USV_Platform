# P0 四人开发进度与联合对接通知

更新时间：2026-09-20。依据已核对的提交、实际验证与同学反馈；未收到交付证据的内容标为待确认，不推测完成率。

## 总体进度

前端和 Java 后端第一阶段已交付，后端 prepare 扩展、画面等待期限和本机隔离环境已完成；当前进入联合对接阶段，真实 Java—Python—Unity 全链路尚未验收。

| 负责人 | 已确认进度 | 证据与边界 | 下一步 |
| --- | --- | --- | --- |
| 同学一：前端 | 上下文匹配、提案创建/确认/取消、执行查询、幂等与刷新恢复、错误展示、展示绑定/挑战/报告 Web 适配；成功后继续查询 PENDING，STALE 提供重新同步入口 | nly/p0-frontend-20260920；e2c9780、26db55c、11a06f1；本机使用包含这些修复的 f5a3dcd 快照；构建通过由前端同学反馈，未证明浏览器闭环 | 接真实接口，验证刷新恢复、展示期限和重新同步 |
| 同学二：后端 mxy | 权限、所有权、运行登记、冻结计划、幂等、持久化/outbox、调度、Java 协议收发/对账、展示接口；E01 prepare 元数据与实际能力；E02 成功后持久化 30 秒展示期限；隔离环境 | e21c27f、760075d；配置与部署 a090ce3；74 项定向回归通过，含继承重复运行，不是 74 个独立业务场景 | 支持真实 runner 与浏览器联调，修复后端问题并记录现场证据 |
| 同学三：Python + Unity | 暂未收到可核验的完整交付记录 | 待确认，不代表未开展开发；后端受控测试进程不算真实算法交付 | 提供分支/commit、依赖、真实 adapter 验证和 WebGL 构建；交付四动作、去重、心跳、查询及展示挑战回执 |
| 同学四：测试 | 团队已有契约、夹具、后端测试和隔离验收模板；尚未收到完整联合验收报告 | 共用资产不作为测试同学个人完成证明；原 76 条及新增用例尚未整体验收 | 建立用例证据映射，组织权限、并发、刷新、超时/迟到、旧代次及 Unity 验收 |

## 隔离环境

前端 http://127.0.0.1:15174；后端 http://127.0.0.1:18081；独立数据库 uav_usv_p0_integration；数据库账号 p0_integration，仅授权该库；网页账号 p0_admin / ADMIN。

密码仅本机保存，不上传 GitHub，也不写入群通知。其他同学参照 [隔离操作清单](integration/README.md) 自行部署；上述回环地址不能从其他电脑访问。共享环境需要另行安排。前端为独立快照，后端分支未合并前端代码；重启时核对实际版本。

实际验证：19 个迁移及 JPA 启动成功、管理员登录成功、上下文查询返回 200、关闭状态下控制请求返回 503 VOICE_CONTROL_DISABLED、专用账号访问原开发库被拒绝。本次同步再次确认后端 health=UP、前端页面 HTTP 200。

P0、Mock、Unity 展示 v1 开关保持关闭，ROS/Gateway/视觉传感器连接关闭。未启动真实算法、未验证 WebGL 回执全链路。

## 接口对齐

- prepare 返回 runtimeRef/runtimeGeneration/protocolVersion/capabilities；来自真实授权协商结果，legacy 返回 null/null/null/[]，见 [E01 说明](prepare-response.md)。
- Python 启动参数为 --command-protocol v1，JSON protocolVersion 为 algorithm.command.v1，RUNTIME_READY 使用 state。
- 展示路由统一为 /api/voice/contexts/{runtimeRef}/presentation 下的 binding、bindings、challenges、reports，不混用旧版 presence/applied。
- START/RESUME 成功后 30 秒无有效画面报告，读取时转 STALE；算法结果保持 SUCCESS。新的合法 FRAME_APPLIED 挑战与帧报告可以恢复 REPORTED_APPLIED，见 [E02 说明](presentation-deadline.md)。
- 不复用过期挑战，不因画面未同步再次发送 START/RESUME；前端修复仍需实际浏览器验证。

## 下一步与负责人

1. 同学三提供 Python/Unity 当前版本与交付状态，同学四记录阻断项。
2. 同学一/二核对登录、上下文、字段、CSRF、错误码；关闭状态不能证明控制链路成功。
3. 真实 runner v1 就绪后，在隔离环境启用并重新 prepare；同学二/三验证四动作、回执关联和心跳。
4. Unity 就绪后，同学一/二/三验证 SUCCEEDED+PENDING、30 秒到期 STALE、重新同步、新挑战、REPORTED_APPLIED，全程算法仍 SUCCEEDED。
5. 同学四组织未知结果、迟到回执、重复确认、刷新、跨用户和旧代次测试，各开发者修复自己模块。
6. 必测项全部 PASS 且有证据后再宣布 P0 完成；构建、Mock、HTTP 202 不能代替验收。

## 可转发通知

各位，P0 前后端第一阶段及后端 prepare 扩展、30 秒画面等待期限已完成，本机隔离数据库、p0_admin 账号和前后端服务已部署并验证，配置与进度说明已同步到 mxy/p0-backend-20260919；前端已包含 11a06f1 的展示轮询及重新同步修复，接下来请 Python/Unity 同学提供真实 runner v1 和 WebGL 交付版本，测试同学组织权限、幂等、刷新恢复及画面超时后新挑战恢复的联合验收，目前功能开关保持关闭，完整链路尚未验收，本机地址不可作为跨机器访问地址。
