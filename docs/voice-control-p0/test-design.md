# P0 测试设计与验收门槛

状态：业务用例设计，尚未实现或运行。fixtures.json 的 SC01—SC39 是单独的结构校验样例，不代替以下测试。

## 1. 测试分层与环境

| 层 | 拟使用方式 | 断言重点 |
| --- | --- | --- |
| Schema | 本目录 validate_contracts.py，已有 jsonschema | 字段、枚举、正反例、共享计划哈希 |
| Java 单元 | 已有 JUnit 5、Mockito、AssertJ | 策略、状态、版本、过期与结果归并 |
| HTTP 安全 | MockMvc + 拟新增 spring-security-test | 会话、CSRF、角色、对象越权、ApiResponse |
| 持久化并发 | 拟新增 Testcontainers MySQL 或专用隔离 MySQL | 唯一约束、确认/取消竞态、事务/outbox |
| Python 协议 | unittest + fake adapter + stdin/stdout harness | 去重、状态边界、异常隔离、回执、退出 |
| Java/Python 联调 | fake runner 进程 + 受控事件脚本 | 断管道、超时、崩溃窗口、旧代次 |
| 前端契约消费 | P0 请求/响应 fixture；P1 再引入 UI 测试运行器 | 明确 202 是入队、确认重试和状态显示 |
| 回归 | 现有测试 + 隔离环境人工验证 | 手动流程、Python 帧和 Unity 协议兼容 |

本项目已有 Spring Boot 测试依赖，但尚未为该功能配置 spring-security-test/Testcontainers；frontend/package.json 也没有统一 test 命令。不要在报告中宣称这些测试已可直接运行。

禁止使用当前 uav_usv_platform 开发库跑破坏性测试。新测试显式使用 test profile、隔离数据库、假进程、禁用 ROS/Unity 自动启动；不加载 application-local.yml 中的开发凭据。现有 PlatformContextIntegrationTests 只是上下文加载检查，不足以证明并发、权限和回执正确。

## 2. 确定性夹具

- 用户 A：ADMIN，拥有实例 R；用户 B：ADMIN，不拥有 R；用户 C：OPERATOR；用户 D：VIEWER。测试数据由夹具预置，不开放认领接口。
- R：MISSION_CENTER / STANDALONE_ALGORITHM / PYTHON_SIMULATION，代次 G1；算法号 7001 是 algorithmRunId，不是数据库 MissionRun 主键。
- 成员：UAV-001、USV-001；首次 stateVersion=3、contextVersion=7、lastFrameSequence=25；可设置 RUNNING 或指定状态。
- 固定 Clock：2026-09-19T08:00:00Z；提案 30 秒过期，心跳 5 秒、场景回执 10 秒有效。
- 替代进程 FakeRunner：可按脚本产生 ready、心跳、ACCEPTED、最终结果、迟到/重复/错代事件及 EOF；业务 apply 计数器独立于日志行数。
- 替代数据库故障注入器：在确认提交前/后、SENDING 持久化后、flush 后、SENT 提交前设置屏障。
- 所有并发测试用 barrier/latch 和注入时钟；不以 Thread.sleep 判断竞争胜负。每条业务用例都检查 DB 记录数、stdin 写入数、apply 次数及最终状态。

## 3. 授权与接口（A 系列）

| ID | 前提 / 操作 | 预期结果与关键断言 |
| --- | --- | --- |
| A01 | 未登录调用所有 P0 端点 | 401；0 提案/执行/管道写入 |
| A02 | A 登录但 POST 缺失或错误 CSRF | 403 CSRF_INVALID；0 副作用 |
| A03 | C/D 调用提案、确认、取消 | 403；不能因前端按钮可见而执行 |
| A04 | B 用 R 的 UUID 查询/写入 | 404，与不存在实例响应一致；不泄露状态 |
| A05 | A 直接调用代理后的应用 Service，随后撤销 ADMIN 再调用 | 首次按权限；撤权后拒绝；不是只测 Controller 注解 |
| A06 | 请求添加 ownerUserId、runId、executionBackend、requiresConfirmation=false | 400；未知字段不被忽略 |
| A07 | body 超过 16 KiB 或 Content-Type 错误 | 413/415；不建立业务资源 |
| A08 | 功能关闭请求写接口 | 503 VOICE_CONTROL_DISABLED；原手动入口仍可工作 |
| A09 | 撤销权限后重放同 Idempotency-Key | 拒绝重放，不从响应缓存泄露已有对象 |
| A10 | GET contexts 无本人实例 | 200 SUCCESS，data=[]；不自动准备实例 |

## 4. 上下文、状态与所有权（R 系列）

| ID | 前提 / 操作 | 预期结果与关键断言 |
| --- | --- | --- |
| R01 | prepare 绑定 A，重复 prepare 同存活进程 | 同一 runtimeRef/G1；不会新建代次或关闭进程 |
| R02 | 替换/重建进程得到 G2，确认 G1 提案 | 待确认提案遇代次变化：409 GENERATION_MISMATCH；进程结束已使提案 INVALIDATED：409 PROPOSAL_INVALIDATED；两者均禁止向 G2 写入 |
| R03 | B 尝试占用 A 的独立槽位 | RUNTIME_BUSY；A 进程不被结束 |
| R04 | 旧实例没有 owner 元数据 | 不认领；写入拒绝，提示重新准备 |
| R05 | 普通 frame sequence 从 25 到 26 | contextVersion 不变，正常确认不被误判过期 |
| R06 | 确认前成员、能力、策略或状态变化 | INVALIDATED/CONTEXT_CHANGED；不能扩大对象集合 |
| R07 | 心跳年龄=5 秒与刚超过 5 秒 | 前者可用，后者 RUNTIME_UNAVAILABLE；使用后端单调钟 |
| R08 | PAUSED 长时间无新 frame，但心跳持续 | RESUME 不因帧旧而被判离线 |
| R09 | START/RESUME 场景报告>10秒；PAUSE/STOP 场景报告失效 | 前两者 SCENE_NOT_READY，后两者在进程健康时可执行 |
| R10 | 只有 legacy ready 或不支持目标 action | PROTOCOL_UNSUPPORTED/UNSUPPORTED_CAPABILITY；零写入 |
| R11 | 非 P0 域、ROS 执行端、数据库 MissionRun 误当独立实例 | 拒绝，不选择“另一个可用实例”兜底 |
| R12 | 每个 action × 每个运行状态参数化 | 与状态表完全一致；终态不可 RESUME |
| R13 | algorithmRunId 为不同于 MissionRun 的值或超过 Long 范围 | 不查询错误业务任务；超范围转换显式拒绝，不溢出 |
| R14 | 已有未知结果 TIMED_OUT，新提案被确认 | EXECUTION_IN_PROGRESS；不得悄悄释放槽位 |

## 5. 提案、幂等与竞争（I 系列）

| ID | 前提 / 操作 | 预期结果与关键断言 |
| --- | --- | --- |
| I01 | 创建提案 | 201；1 提案、0 execution、0 stdin 写入；30秒窗口 |
| I02 | 同用户/operation/键/内容重复创建 | 200；仍为同一 proposalId，不延长 expiresAt |
| I03 | 同键不同 body 或动作 | 409 IDEMPOTENCY_CONFLICT；原计划不变 |
| I04 | 同键不同用户或不同资源 operation | 不串资源；分别按权限及作用域处理 |
| I05 | I05-a：expectedPlanVersion=2；I05-b：版本为1且哈希格式合法但不匹配 | a：400 INVALID_REQUEST；b：409 PLAN_MISMATCH。两者均 0 execution/outbox/管道写入，原提案不变；取消使用相同规则 |
| I06 | now 比 expiresAt 小1ms、恰好相等、超过1ms | 前者可确认；后两者 EXPIRED；边界使用固定时钟 |
| I07 | 10个并发确认同提案，使用不同键 | 1 execution、1 outbox；有效写入/apply 各至多1次；均关联同执行 |
| I08 | 同一个确认响应丢失，再确认已 CONFIRMED 提案 | 返回原执行最新状态；不按已过的提案窗口生成第二次动作 |
| I09 | confirm 与 cancel 并发屏障释放 | 只有一方赢；取消赢零写入，确认赢取消409 |
| I10 | 重复 cancel；取消已确认或已失效提案 | 重复取消幂等；已确认409；不向 runner 发任何撤销动作 |
| I11 | 确认与手动状态操作并发 | 实例锁与发送前校验保证过期计划不覆盖手动状态 |
| I12 | Java/Python 对 fixtures 黄金计划计算哈希 | 得到相同 canonicalJson/sha256；设备输入顺序不同由计划构造规范化 |

## 6. Python 协议与事件归并（P 系列）

| ID | 前提 / 操作 | 预期结果与关键断言 |
| --- | --- | --- |
| P01 | 正常 START/PAUSE/RESUME/STOP | ACCEPTED→SUCCEEDED；commandId/代次相同，状态符合表 |
| P02 | 同 commandId 同内容投递两次 | apply=1；返回原缓存事件序号/内容 |
| P03 | 同 commandId 改 action/参数 | PROTOCOL_ERROR(COMMAND_ID_CONFLICT)；apply 不增加，原命令结果不改变 |
| P04 | 未知 ID 使用旧/跳跃 commandSequence | SEQUENCE_MISMATCH；不推进 lastCommandSequence |
| P05 | 合法序号但业务状态不合法，再发下一个序号 | 首条 REJECTED 且消费序号；下一合法命令正常，不堵队列 |
| P06 | expectedStateVersion 已落后 | STATE_VERSION_MISMATCH；不执行过期动作 |
| P07 | 非法 JSON、未知 action、额外参数、适配器业务异常 | 不返回成功；无效业务动作不杀进程；合法后续动作可继续 |
| P08 | Java 接收 commandResult 而非 stateChanged | 只有关联回执可结算；stateChanged 单独不完成 execution |
| P09 | 错 runtimeRef/代次/来源进程、未知 commandId | 隔离事件；当前执行和运行状态均不改变 |
| P10 | 重复 eventSequence；同序号不同内容 | 重复无新事件；冲突记协议错误，不覆盖可信状态 |
| P11 | SUCCEEDED 后收到旧 ACCEPTED；旧代次迟到 SUCCEEDED | 不回退终态；旧执行可对账但新代次不变 |
| P12 | PAUSE 后没有新 frame | 状态回执足以成功；lastFrameSequence 保留25，无无限等待 |
| P13 | STOP 最终回执后进程退出；回执前 EOF | 前者成功且清理；后者未知/失败证据处理，不预设成功 |
| P14 | 自然 COMPLETED/FAILED 后发送 RESUME | 拒绝；不调用适配器 set_mission_active |
| P15 | result 中 affectedDeviceCodes 与计划不同 | 协议异常，不结算成功；不扩大为全部设备 |
| P16 | 连续3个超大/身份违规行、普通 stdout 日志 | 有界内存，通道不可用；普通日志不当执行事件 |
| P17 | 缓存10000命令后新命令；重复旧命令 | 新命令 CAPACITY_EXCEEDED，旧命令仍可查，无去重淘汰 |
| P18 | STATUS_QUERY 查询已知/未知/退出实例 | 只读；不消费 commandSequence、不调用 apply；UNKNOWN 不重发 |
| P19 | PAUSED 心跳持续与 worker 真正死锁 | 暂停在线；不能让独立心跳掩盖无法应用动作 |
| P20 | Result 与 QueryReply 内层关联 ID 不一致 | 语义校验拒绝；Schema 正确也不等于可信关联 |

## 7. 数据库和故障窗口（F 系列）

| ID | 故障窗口 / 操作 | 预期结果与关键断言 |
| --- | --- | --- |
| F01 | 确认事务提交前异常 | proposal/execution/outbox 原子回滚；零管道写入 |
| F02 | 确认已提交，worker 还未领取 | 只有 READY，可按未发送状态复检后发送一次 |
| F03 | SENDING 持久化后、write前崩溃 | UNCERTAIN；不自动重发；即使实际零写入也按不确定处理 |
| F04 | flush后、SENT提交前崩溃 | 不重复发送，查询或保持未知；apply至多1 |
| F05 | 回执已到但落库失败 | 暂停新发送，恢复后查询/补账；不可报持久化成功 |
| F06 | ACK 5秒/结果15秒边界，模拟快终态无单独ACK | 正确超时或结算；最终结果可满足接收要求 |
| F07 | 超时后迟到可信终态 | 保留 timedOutAt，更新最终结果，不触发第二次命令 |
| F08 | 后端重启/管道所有权丢失 | 原代次LOST；旧未确认失效；已发送保持未知，不重放到新进程 |
| F09 | outbox READY 10秒未领取 | INVALIDATED、DISPATCH_DEADLINE_EXCEEDED；零写入 |
| F10 | 执行处于不确定状态时清理任务运行 | 审计/去重记录保留；不能因TTL删掉唯一约束依据 |
| F11 | 单实例两个 worker 同时领取 | 数据库条件更新只允许一个领取者；无重复写入 |
| F12 | worker发送前撤权/换代/成员变化 | INVALIDATED；撤权后不因已确认绕过鉴权 |

## 8. 兼容与显示回归（C 系列）

| ID | 操作 | 预期结果 |
| --- | --- | --- |
| C01 | 功能关闭，运行旧手动算法接口 | 原路径可用，接口字段和旧枚举保持兼容 |
| C02 | v1实例通过旧手动按钮发动作 | 适配到同一命令队列；不混入无ID命令 |
| C03 | API 202 QUEUED 返回前端 | 显示已受理/等待执行，不能显示完成 |
| C04 | 算法SUCCEEDED但Unity断开/报告过期 | 分别显示执行生效与画面未同步 |
| C05 | 换页面/刷新/iframe实例改变后迟到画面报告 | 不影响新上下文；不将显示报告当算法执行结果 |
| C06 | 两套Unity消息、算法原frame恢复流程 | 既有位姿/坐标/帧序号兼容，无第二套重复驱动 |
| C07 | 旧任务、设备控制与登录回归 | 原有权限不被语音入口弱化，现有手动路径通过回归 |
| C08 | 日志/错误/fixture检索 | 无API密钥、数据库密码、Cookie或用户原始音频 |

## 9. 建议实现顺序与测试落点

1. ContractValidationTests + Python 协议夹具：先消费相同 Schema/黄金哈希，不接云模型。
2. RuntimeContextRegistryTests、VoicePolicyTests：R系列与A系列服务层规则。
3. VoiceProposalControllerTests + VoiceProposalConcurrencyIT：A/I系列，以真实数据库验证唯一约束，不能只用 mock repository。
4. test_command_protocol.py + AlgorithmCommandResultTests：P系列，替换假adapter观察真实apply计数。
5. VoiceOutboxRecoveryIT：F系列，逐个崩溃窗口设置可重复屏障。
6. LegacyCommandCompatibilityTests、前端契约与人工画面验证：C系列。

以上类名为拟建测试，不表示仓库中已存在。禁止为了使测试通过，只模拟一个“永远返回成功”的执行器并据此宣称跨进程链路通过。

## 10. 退出门槛与证据格式

P0 实现交付需要上述 A/R/I/P/F/C 用例全部有结果；高风险拒绝、竞态和崩溃窗口不得跳过。每条结果包含 ID、代码版本、环境、执行时间、PASS/FAIL/BLOCKED、证据路径、DB计数、write/apply计数及已知限制。

并发用例 I07/I09/F11 建议至少重复100次且无重复动作；该次数是后续验收要求，本次未执行。Python 假进程及真实轻量adapter分别验证，禁止使用真实载具代替测试替身。

设计阶段完成标准：契约数据结构、状态/错误/权限/幂等规则明确，正反例和黄金哈希自检通过，业务测试设计可追溯。此标准不等于 P0 业务功能已完成。

## 附：Schema 验证之外的必需断言

JSON Schema 不验证数据库授权、UUID是否真实存在、跨对象身份相等、planHash真实值、设备数组排序、时间先后、版本推进、outcome与历史因果或“最多一次”。这些必须由上述测试承担。SC样例只证明格式约束，不能作为安全或并发验收结论。