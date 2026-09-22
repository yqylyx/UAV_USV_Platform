# P0 真实 Runner 与 Unity 接入核验记录

核验日期：2026-09-21。仅使用本机隔离数据库和仿真进程。未连接实机，未推送或合并同学分支。

## 核验基线

- Python：origin/zsj/p0-python-20260921，057798726929e0ff7ee8cfb8e2cc8c8b16e210f9。
- Unity：origin/zsj/p0-unity-20260921，7fb0cbfe93a48616d53440e000d1bf959ef99c55。
- 前端隔离快照：f5a3dcdda261c6b08446efde60d85d195d9f0eea，包含本机总览加载路径修复。
- 后端：当前 mxy 工作区已构建的隔离服务，包含本机未提交修复；不视为完全干净的提交基线。

## 实测结果

| 项目 | 结果 | 说明 |
|---|---|---|
| Python 真实算法进程启动 | 通过 | GB_SFLA_CS，真实 adapter，非 Fake Runner |
| RUNTIME_READY | 通过 | PREPARED；身份字段及消息结构检查通过 |
| 初始算法帧 | 通过 | sequence=1 |
| HEARTBEAT | 通过 | 正常接收，暂停期间也可收到 |
| START/PAUSE/RESUME/STOP | 协议回执通过，业务完整性未通过 | 顺序返回 SUCCEEDED，状态依次 RUNNING/PAUSED/RUNNING/STOPPED；四次 affectedDeviceCodes 都为空 |
| STOP 后退出 | 通过 | 回执后进程退出码 0 |
| Java 启动真实 Runner | 通过 | runId=990022，prepare HTTP 200，返回 runtimeRef/runtimeGeneration/v1/四动作能力 |
| Java 接收真实心跳 | 通过 | contexts 中实例为 PREPARED，心跳时间更新 |
| Java START | 阻断 | HTTP 409，CONTEXT_CHANGED；尚不能宣称 Java 四动作链路通过 |
| Unity 展示闭环 | 未通过验收 | 静态发现消息入口不兼容，尚未进行真实浏览器与 Unity 帧应用验收 |

## 阻断一：算法帧设备标识不一致

真实初始帧 agents 使用 code，例如 UAV-001、USV-001；Runner 新增的 _device_codes 只读取 deviceCode，后端 RuntimeContextRegistry.frame 同样只读取 deviceCode。导致后端权威成员名单为空，START 校验返回 CONTEXT_CHANGED；独立 Python 四动作的成功回执设备列表也为空。

建议成员三在输出帧边界补齐契约要求的 deviceCode，并保留旧 code 以兼容原展示；确保 affectedDeviceCodes 与该帧权威成员一致。成员二配合检查成员提取和回执核对，不能以放宽空名单检查作为修复。成员四添加使用真实 adapter 帧的回归用例，避免仅用手写 deviceCode 夹具遗漏问题。

## 阻断二：Unity 网页消息入口不兼容

前端 SimulationUnityWebglPanel 发送原始 PRESENTATION_HELLO/PROBE 消息；Unity 的 VueWebGlVirtualFleet.index.html 模板入口要求 data.source 为 vue-console 且存在 data.message，原始消息会被丢弃。模板 dispatchToUnity 也未包含新 PRESENTATION 消息分派。仅新增 C# 接收逻辑不足以完成网页到 Unity 的调用。

成员一与成员三应统一网页消息封装、来源检查及 Unity 接收方法，更新模板并重新构建实际部署的 WebGL。当前提交中的 C# 编译成功不能替代 WebGL 展示闭环证据。

## 下一轮执行顺序与分工

1. 成员三修正帧设备字段和成功回执设备名单；成员二重跑真实 prepare、Ready、心跳和 Java 四动作，记录 execution 与 commandId 对应关系。
2. 成员一、三修正消息桥并提供新 WebGL，成员二核对绑定及 challenge API。
3. 四人联调 SCENE_READY → 提案确认 → 算法 SUCCEEDED → FRAME_APPLIED → REPORTED_APPLIED。
4. 成员四组织 PENDING 超过 30 秒转 STALE、废弃旧挑战后重新同步、旧 binding/generation/challenge 拒绝，以及刷新恢复等验收。
5. Unity 必须在真正成功应用画面后报告帧序号；另需复核代码中应用调用前更新 presentationFrameSequence 的逻辑，失败应用不得被报告为成功。

## 证据及环境恢复

本机忽略目录 .local-tools/p0-integration 中保存 runner-real-events.json、runner-real-stderr.log、java-real-runner-check.json。它们为本机测试证据；凭据另行隔离，不应上传。

核验后后端恢复 app.voicecontrol.enabled=false，并恢复原 Runner 路径。未开启前端 Unity v1 展示开关。修复上述阻断前，不宣称完整 P0 联合验收完成。
