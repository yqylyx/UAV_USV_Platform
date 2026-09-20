# UAV-USV Platform Frontend

Vue 3 + TypeScript + Vite 前端工程，用于 UAV-USV 海空协同仿真与任务控制平台。

## 技术栈

- Vue 3
- TypeScript
- Vite
- Pinia
- Element Plus
- Lucide Icons

## 当前页面

- 登录页
- 系统总览
- 设备管理
- 运行监控

## 页面设计原则

- 页面优先围绕任务闭环设计，不做普通后台堆表格。
- UAV、USV、ROS、Unity 等对象应以任务资产和态势节点方式展示。
- 查询、筛选、按钮、状态等控件需要保持紧凑和可扫描。
- 与 PPT 对齐，优先形成深蓝科技风格的任务控制台。

## 后续页面

- 任务控制 / 任务配置
- 通信网络监控
- 协同围捕过程展示
- 实验评估与回放

详细规划见根目录 [docs](../docs/README.md)。

## 语音大模型控制 P0 前端

算法仿真工作区已经接入 `voice-p0.v1` 的前端控制面板。当前范围是后端已识别意图后的任务级控制：开始、暂停、继续、停止。所有写操作均先创建冻结计划，用户在弹窗中核对设备快照、版本和哈希后再确认下发；页面刷新后会按提案/执行 ID 恢复状态。

真实模式默认请求以下接口：

- `GET /api/voice/contexts`
- `POST /api/voice/commands/proposals`
- `GET /api/voice/commands/{proposalId}`
- `POST /api/voice/commands/{proposalId}/confirm`
- `POST /api/voice/commands/{proposalId}/cancel`
- `GET /api/voice/executions/{executionId}`
- `GET /api/voice/contexts/{runtimeRef}/presentation/binding`
- `POST /api/voice/contexts/{runtimeRef}/presentation/bindings`
- `POST /api/voice/contexts/{runtimeRef}/presentation/challenges`
- `POST /api/voice/contexts/{runtimeRef}/presentation/reports`

写请求携带 CSRF 头和独立的 `Idempotency-Key`。真实接口失败时不会自动切换为 Mock。

前端按当前算法页面的十进制字符串 `algorithmRunId` 精确匹配上下文，不默认使用列表第一项。页面可见时约每 3 秒刷新上下文；动作前立即刷新；心跳超过 5 秒、场景证据不新鲜、协议或能力不匹配、有未决执行时均禁用相应动作并显示原因。

每次 POST 在发出前会按当前登录用户名隔离保存最小恢复日志，包括运行身份、路径、原始最小 body 和幂等键。发生网络中断或 5xx 时，不生成新键重发；刷新或点击“核对上次请求”会先读取权威资源，必要时以原 body 和原键重放。退出登录会清理该用户的本地恢复数据。

展示 binding、`SCENE_READY/FRAME_APPLIED` challenge/report 以及 Web 侧 `unity.presentation.v1` 适配器已经接入。适配器会严格检查 iframe `source`、精确 origin、运行身份、binding、`unityInstanceId`、`sceneRevision` 和一次性挑战字段，再把闭合的报告 body 提交后端。旧 `scenarioReady/poseFrameApplied` 回调不会被伪装成本轮挑战证据。

Unity 侧完成并冻结 E03 协议前保持 `VITE_VOICE_UNITY_PRESENTATION_V1=false`。完成后在隔离联调环境显式设置为 `true`，前端才会建立/替换展示绑定、进行最长 30 秒 HELLO/READY 握手，并串行执行约 3 秒一次的场景新鲜度探测；START/RESUME 成功且展示为 PENDING 时优先执行 FRAME_APPLIED 探测。

后端接口尚未就绪时，可复制 `.env.example` 为 `.env.local`，显式设置 `VITE_VOICE_P0_MOCK=true` 后重启 Vite。页面会显示“本地 MOCK”标记，并可演示成功、拒绝、失败和“超时后迟到成功”；这些结果不会控制 Python 算法或 Unity。

麦克风采集、ASR、LLM 意图解析、撤退/围捕/攻击等新算法动作，以及单个无人机/无人艇控制不在 P0 接口范围内，待后端和算法侧扩展契约后接入。
