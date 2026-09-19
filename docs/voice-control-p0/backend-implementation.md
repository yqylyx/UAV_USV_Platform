# P0 Java 后端实现与交接说明

日期：2026-09-19。范围：v3.0 分工中的同学二（BE01—BE09），以及后端自身验证。本文不宣布前端、真实 Python runner 或 Unity 已完成。

## 1. 本次实现

| 任务 | 对应实现 | 行为 |
| --- | --- | --- |
| BE01 | RuntimeContextRegistry、VoiceRuntimeBridge | prepare 登记 owner/运行身份/代次，成员集合、状态版本、心跳和场景证据 |
| BE02 | VoiceController、VoiceAccess、VoiceHttpFilter | 七个业务接口，当前账号数据库复检，应用服务权限，CSRF、16 KiB 流式限制、严格字段检查 |
| BE03 | VoiceCommandApplicationService | 不可变计划、黄金哈希、30 秒过期、确认复检、确认/取消竞争 |
| BE04 | VoiceStore、V19 迁移 | 提案、执行、幂等、outbox、事件、诊断审计；数据库唯一约束和事务 |
| BE05 | VoiceDispatcher | 实例未决执行占槽，SENDING 提交后发送，命令序号，发送前再次鉴权 |
| BE06 | VoiceDispatcher、现有 AlgorithmRuntimeManager | 绑定实际进程读取器，校验回执，去重、拒绝冲突、终态不回退 |
| BE07 | VoiceDispatcher | 超时 UNKNOWN、只读查询、迟到终态核对、重启 LOST、不自动重发 |
| BE08 | VoicePresentationService、VoiceRuntimeBridge | 就绪证据链、手动入口进入同一调度器、默认关闭、在途执行继续核对 |
| BE09 | 本文及测试 | 配置、迁移、协作样例、测试命令与完成边界 |

模块位置：`backend/src/main/java/com/uavusv/platform/module/voicecontrol/`。

没有改动 `algorithm-service` 的真实运行代码，也没有改前端和 Unity 业务代码。`backend/src/test/resources/voicecontrol/contract_runner.py` 仅为后端管道验证替身，不是给项目使用的算法 runner，更不表示算法协议工作已替第三位同学完成。

## 2. 数据库与部署约束

新增 `V19__create_voice_control_p0.sql`。实施前已确认原迁移最大版本为 V18。本次开发测试在独立数据库执行，没有将 V19 应用到正在使用的开发库。

表：`voice_control_lock`、`voice_runtime_context`、`voice_proposal`、`voice_execution`、`voice_outbox`、`voice_idempotency`、`voice_command_event`、`voice_audit`。

P0 只有一个独立仿真槽位，使用数据库锁行串行化短事务，包括跨线程的确认/取消与 worker 领取；管道写入不在数据库事务内。业务快照以私有 JSON 保存，身份/所有权/执行状态和幂等关键字段单独索引。执行、outbox 和回执唯一约束在数据库落地。

当前运行器由本机 Java 进程持有，部署方式为**单个后端进程独占这一套数据库与运行槽位**。不能把本版本直接横向扩容为多个独立后端节点；多节点需要额外实现进程所有权租约和恢复策略。并发 worker 测试不等于多节点部署验证。

没有自动删除幂等或审计记录，故不会提前清除未知结果；正式长期运行的归档策略需要后续单独制定，至少满足 30 天及关联执行已终结的条件。

## 3. 启用与兼容

默认配置：

```yaml
app:
  voicecontrol:
    enabled: ${VOICE_CONTROL_ENABLED:false}
    poll-ms: 200
```

- 当前功能默认关闭。不要在第三位同学尚未实现 v1 Python 参数和消息时开启；旧 runner 不识别新参数会明确启动失败。
- 开启后只对新建的 standalone Python 实例协商 v1；现存 legacy 进程不热切换。
- 新进程增加 `--command-protocol v1 --runtime-ref <UUID> --runtime-generation <UUID>`。
- 旧手动 START/PAUSE/RESUME/STOP 在 v1 实例上进入相同持久化队列，记为 MANUAL，不直接写裸 action。
- v1 不支持 CANCEL、PLACE_THREAT、ACTIVE_CAPTURE；这些不属于 P0 四动作。legacy 模式保留已有行为。前端同学必须将 P0 停止操作对接 STOP。
- 已受理执行不因开关关闭而撤销；关闭后禁止 P0 新写入，GET、回执、对账继续工作。关闭开关不会把已有 v1 进程变回 legacy。
- 配置启停通常需要重启应用；进程内提供受控设置点用于测试，不提供可被浏览器修改的开关接口。重启会丢失进程代次，走 LOST 规则，不能宣称这是无损的在线开关切换。
- standalone 实例所有权在原 prepare/读取/手动操作入口也检查，避免跨用户替换或控制其他人的运行实例。

配置和运行命令使用各人本地环境，不把数据库密码、会话 Cookie 写入示例或 Git。

## 4. 控制接口

认证沿用现有登录会话。POST 使用 `/api/auth/csrf` 返回的 headerName/token，并传 `Idempotency-Key: <小写 UUID>`。所有响应 `Cache-Control: no-store`。

| 方法 | 路径（前缀 `/api/voice`） | 首次成功 |
| --- | --- | --- |
| GET | `/contexts` | 200 |
| GET | `/contexts/{runtimeRef}` | 200 |
| POST | `/commands/proposals` | 201，重放 200 |
| GET | `/commands/{proposalId}` | 200 |
| POST | `/commands/{proposalId}/confirm` | 202，已确认重放 200 |
| POST | `/commands/{proposalId}/cancel` | 200 |
| GET | `/executions/{executionId}` | 200 |

创建提案：

```json
{
  "runtimeRef": "11111111-1111-4111-8111-111111111111",
  "runtimeGeneration": "22222222-2222-4222-8222-222222222222",
  "expectedContextVersion": 7,
  "intent": "MISSION_PAUSE"
}
```

确认和取消的 body 都来自已查询提案：

```json
{
  "expectedPlanVersion": 1,
  "expectedPlanHash": "e15c6ce6c4a0de1555daabcaaa77e64ca653e4d400a98e615af265c02f29e656"
}
```

UUID 和哈希为契约样例；联调时使用当前服务返回的真实值。确认/取消各有独立操作幂等作用域。重复请求返回资源的最新状态，不缓存未经重新鉴权的旧 HTTP 响应。

错误响应沿用 `code/message/data/timestamp`，`data=null`。P0 登录/CSRF 错误采用契约中的 `UNAUTHORIZED/CSRF_INVALID`；旧接口继续使用原错误码。

## 5. K04 补充契约：浏览器展示证据

这是原七个控制接口之外的展示状态补充，不是动作执行接口。新增请求定义已写入 `contracts.schema.json` 并同步到后端资源目录；原控制请求形状不变。

路径前缀：`/api/voice/contexts/{runtimeRef}/presentation`。

| 方法与路径 | 用途 |
| --- | --- |
| GET `/binding` | 当前绑定 ID 和运行代次；绑定尚不存在时 ID 为 null |
| POST `/bindings` | 按 expectedBindingId 比较并替换绑定，清除旧场景就绪状态 |
| POST `/challenges` | 为当前绑定签发一次短期请求关联标识 |
| POST `/reports` | 接收关联证据，验证代次、绑定、挑战和一次性消费 |

四个入口均校验登录和实例所有权，三个 POST 均需 CSRF 和 Idempotency-Key。展示上报不改变算法 execution 的成功/失败状态。

### 5.1 页面绑定

GET 取得当前 bindingId；POST `/bindings`：

```json
{
  "runtimeGeneration": "22222222-2222-4222-8222-222222222222",
  "expectedBindingId": null
}
```

第一次是 null；显式页面接管/重载时提供刚查询到的旧 ID。服务返回新的 bindingId。旧页面不得在失败后自动循环抢占绑定；接管应来自当前页面初始化或明确的用户操作。

### 5.2 新鲜场景就绪

POST `/challenges`：

```json
{
  "runtimeGeneration": "22222222-2222-4222-8222-222222222222",
  "bindingId": "33333333-3333-4333-8333-333333333333",
  "kind": "SCENE_READY",
  "executionId": null
}
```

服务返回上述字段及 `requestId`、`sequence`、`expiresAt`。挑战有效期 5 秒，同一绑定仅保留当前挑战；下一挑战替代上一挑战。同学一在取得挑战后，必须向当前 iframe 发起新的就绪确认，并检查消息 source、origin、页面绑定和关联请求。同学三提供实际场景就绪响应，统一使用 `scenarioReady`。

收到当前请求的 Unity 回执后，POST `/reports`：

```json
{
  "runtimeGeneration": "22222222-2222-4222-8222-222222222222",
  "bindingId": "33333333-3333-4333-8333-333333333333",
  "kind": "SCENE_READY",
  "executionId": null,
  "requestId": "44444444-4444-4444-8444-444444444444",
  "sequence": 1,
  "frameSequence": 1,
  "applied": true
}
```

证据被接受后 sceneReady 默认有效 10 秒。重新确认需要新的挑战与真实 iframe 响应；同一报告重放不会续期。`applied=false` 使就绪状态失效。frameSequence 不得超出后端已观察到的权威帧序号。

开始/恢复前可重新探测就绪；暂停/停止无需依赖新场景证据。iframe 重建时先替换绑定，使旧就绪状态失效。单个绑定的挑战和报告应顺序执行，避免多个探测相互覆盖。

### 5.3 画面应用报告

算法 START/RESUME 已 `SUCCEEDED` 后，以 `kind=FRAME_APPLIED`、对应 `executionId` 申请挑战；其他字段流程一致。报告帧序号至少覆盖该命令回执中的 lastFrameSequence，且不大于后端已收到的帧序号。

合法报告只能把 presentationStatus 标为 REPORTED_APPLIED。绑定改变或场景证据过期后读取显示 STALE；PAUSE/STOP 默认 NOT_REQUIRED。

后端无法独立证明浏览器真的渲染成功；这是经过授权和关联校验的页面报告，不是硬件证明，也不能替代 Python 的执行回执。

## 6. 给第三位同学的 Python 接口要求

1. 使用后端传入的身份，输出 Schema 定义的 `RUNTIME_READY`；旧的 `event=runtimeReady` 不算 v1 协商成功。
2. 保留原 `event=frame,payload=...` 链路，agents 中提供 canonical `deviceCode`。Java 从权威帧提取冻结成员集合。
3. PREPARED/PAUSED 也要持续 HEARTBEAT；身份、stateVersion、heartbeatSequence、lastFrameSequence 都按 Schema。
4. 接收 COMMAND，先 commandId 去重，再检查序号，串行应用四动作。
5. 输出关联 COMMAND_RESULT。SUCCEEDED 的受影响成员须等于冻结集合，目标状态正确，stateVersion 对本动作递增一次。
6. STOP 最终回执先 flush 再退出；stdout 保持受支持 JSON 事件，普通日志写 stderr。
7. STATUS_QUERY 仅查询缓存，不应用动作；结果未知不构成后端重发许可。
8. PROTOCOL_ERROR 不覆盖原命令结果。身份/序号错误使通道进入保守只读核对。

请直接使用既有 `algorithm-protocol.md` 与 JSON Schema；不要参照测试替身省略生产端去重、异常或容量控制。

## 7. 失败处理与可用性边界

- QUEUED 超过 10 秒且尚未发送：INVALIDATED，零管道写入。
- flush 后 5 秒无 ACK，或 15 秒无终态：TIMED_OUT / UNKNOWN。
- 原代次仍存活时最多三次只读查询，间隔 2 秒；不会自动再发 COMMAND。
- SENDING 与管道 flush 之间的崩溃窗口按不确定处理；宁可保留 UNKNOWN，也不声称分布式“恰好一次”。
- 数据库暂时不可用时暂停新调度，保持进程读取；待落库事件使用有界内存缓冲，恢复后核对。缓冲溢出使通道只读，不能保证进程和数据库同时丢失时恢复全部证据。
- 重启不复用旧进程身份，不自动重放旧命令；原代次 LOST，未知执行继续保留 UNKNOWN。
- 无定时清理未知执行。需要重新运行时由用户显式重新 prepare，创建新的运行身份/代次。

## 8. 后端验证方式

在平台根目录，使用 JDK 17 或 21；当前验证环境为 JDK 21。

只运行本次后端测试（隔离 H2 与受控管道，不加载开发数据库配置）：

```powershell
mvn.cmd -f backend/pom.xml "-Dtest=VoiceControlTests,VoiceHttpTests,VoiceProcessTests" test
```

可选 MySQL 测试：设置 `VOICE_TEST_MYSQL_URL`（服务器根 URL，不能包含开发数据库名）、`VOICE_TEST_MYSQL_USER` 和 `VOICE_TEST_MYSQL_PASSWORD`，运行：

```powershell
mvn.cmd -f backend/pom.xml "-Dtest=VoiceMysqlTests" test
```

示例 URL：`jdbc:mysql://127.0.0.1:3306/?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC`。账号需有创建/删除独立测试数据库权限；测试只处理本次随机创建的 `uav_usv_p0_test_<32位十六进制>` 库。

现有 PlatformContextIntegrationTests 会启动整个应用。运行全量测试时必须覆盖 datasource、禁用 local profile、禁用外部集成，并提供测试用 bootstrap 和 integration 配置，不能直接让它连接开发库。完整启动应同时验证 V1—V19 的 Flyway 迁移和 JPA 映射。

Schema 自检：

```powershell
python docs/voice-control-p0/validate_contracts.py
```

后端测试还校验文档 Schema 与打包资源一致，防止修改一份、遗漏另一份。

### 测试结果解释

本次 JUnit 用例是后端实现验证，与原 76 条跨模块业务设计不是一一计数关系；H2/MySQL 的同一测试重复运行也不增加业务覆盖种类。真实 Python 算法 v1、Unity 同步和四人联合端到端尚需各负责人交付后验收。

运行结果及用例名称见 `backend/target/surefire-reports/`，该目录为本机构建产物，不应把含环境信息的全部报告直接提交仓库。

## 9. 合并与回滚

1. 合并前确认团队没有另一份 V19 迁移；如发生编号冲突，在任何共享环境应用前统一编号。
2. 合并同一版本的 Java 模块、迁移、Schema 和本文。
3. 首次启动由 Flyway 应用 V19，默认仍不启用 P0 控制。
4. 前端和真实 runner 完成后，使用隔离演示环境启用并重新 prepare，再进行四人联合验收。
5. 禁用功能不删除已受理执行；数据库迁移是新增表，回退代码时优先保留新增表和审计记录。
6. 不通过手动修改已成功执行的迁移文件或清空 execution/outbox 来消除未知结果。

## 10. 仍需其他同学对接的内容

- 同学一：七个业务接口、展示绑定/挑战/报告、202 与算法成功区分、页面恢复和旧 iframe 隔离。
- 同学三：真实 runner v1 参数/协议、去重与心跳，Unity 新鲜就绪探测、位姿展示和独立回执。
- 同学四：把后端测试映射进全项目验收表，补充跨模块故障、浏览器与 WebGL 验收证据。

K04 的本版字段和单挑战行为应在联调前由前端/Unity/测试同学确认；不同实现建议需通过更新 Schema、fixtures 和本文统一，不能各自修改字段。

实际测试结果见 [backend-validation.md](backend-validation.md)。

## E01 增量：prepare 响应

prepare/status/动作共用响应已补充 runtimeRef、runtimeGeneration、protocolVersion、capabilities；从授权后的持久化握手快照读取，legacy 返回 null/null/null/[]。详见 [prepare-response.md](prepare-response.md)。本增量的实际测试记录单列，不能沿用此前 203/70 的计数。

## E02 增量：画面等待期限

START/RESUME 成功后持久化 30 秒展示期限，读取时将到期 PENDING 结算为 STALE；合法迟到画面证据可恢复已报告。详见 [presentation-deadline.md](presentation-deadline.md)。
