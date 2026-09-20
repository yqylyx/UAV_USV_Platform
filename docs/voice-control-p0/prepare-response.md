# E01 prepare 响应扩展与前端交接

已补充实现，随 mxy/p0-backend-20260919 分支交付；未重启服务。适用于现有 `POST /api/algorithm-runs/{runId}/prepare`；共用 DTO 的 status 和动作响应同步包含扩展字段。ApiResponse 包装不变。

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| runtimeRef | string / null | 已成功协商 v1 的实例身份 |
| runtimeGeneration | string / null | 对应进程代次 |
| protocolVersion | string / null | 成功协商为 algorithm.command.v1 |
| capabilities | string[] | 已验证并持久化的 runner 实际能力子集；不根据算法名补齐 |

原 runId、algorithmCode、state、latestSequence、error、latestFrame 的名称和类型不变。新字段从当前用户有权读取的持久化上下文快照取得，并核对进程代次；不读取启动时尚未更新的能力数组。非 standalone、legacy、Unity 原生实例或尚未完成 v1 握手时，三个身份/协议字段为 null，capabilities=[]。已协商后运行结束并不抹去身份，它仍用于关联历史；能力声明不等于当前动作可用，前端仍需读取上下文检查状态/心跳等条件。

准备失败继续抛出原错误响应，不包装成一个伪成功 prepare 对象。首次准备必须通过既有 ready 和首帧等待；本次不改变超时阈值。

前端收到 v1 元数据后，可使用 runtimeRef 读取 `/api/voice/contexts/{runtimeRef}` 获取 contextVersion、状态与就绪条件，再创建提案。重复 prepare 同一存活进程返回同一身份；重建进程产生新代次。客户端 TypeScript 将新增字段标为可选，以兼容后端尚未升级的部署；新后端固定返回这些字段。

机器结构见 [prepare-response.schema.json](prepare-response.schema.json)。这是 prepare 的 data 定义，不改变既有 voice-p0 请求 Schema，也不替代 runtime context 定义。latestFrame 延续原帧载荷，此文件只约束其为对象或 null。

验证覆盖：真实子进程测试替身握手、实际能力子集、重复准备身份稳定、替换进程换代、准备失败、跨用户拒绝、错误代次拒绝、旧算法回归。此测试替身不等于生产 Python v1 已交付。

E01 已完成；后续 E02 展示等待期限也已补充，见 [presentation-deadline.md](presentation-deadline.md)。功能默认关闭，未修改开发数据库。

## 本次验证结果（2026-09-19）

- 首轮定向回归：VoiceProcessTests 33、VoiceHttpTests 6、AlgorithmRuntimeManagerTests 5，共 44 项通过。
- 增加 Unity 原生模式兼容用例后：AlgorithmRuntimeManagerTests 6 项通过，与首轮有重叠，不累加计算。
- 原契约 48 个正反例、黄金哈希、文档链接与围栏检查通过；新增 prepare 响应 6 个正反例通过。
- 前端 vue-tsc 类型检查通过；限定本次修改的 git diff --check 通过。
- 测试使用 H2 与受控 Python 子进程，以及原 legacy 算法回归；未重启项目服务、未运行开发库迁移、未验证生产 Python v1 或实际 WebGL。
