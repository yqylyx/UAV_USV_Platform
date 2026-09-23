# P0 本机隔离验收完成报告

日期：2026-09-22。**当前96条覆盖清单全部通过：96 PASS，0 PARTIAL，0 FAIL。**

范围为当前工作区的P0任务提案、权限/幂等/并发、Java—真实Python Runner、Unity WebGL展示和恢复链路。未将后续麦克风、语音识别或大模型解析阶段计入P0。

## 最终受测版本与服务

- 分支：`mxy/p0-local-acceptance-20260922`；基础提交 `ae46345f`，叠加本地修复。验收当时为本地未提交修复；本报告现随修复一起发布至该分支，发布与合并事项见 [交接说明](P0-PUBLISH-HANDOFF-20260923.md)。不代表主分支或测试基线已自动合入。
- 本机隔离MySQL：`uav_usv_p0_integration`，未连接远程数据库。MySQL专项只创建/删除随机测试自有数据库。
- 前端 `http://127.0.0.1:15174/`，后端 `http://127.0.0.1:18081/`。
- 收尾后 `voiceEnabled=false`、`unityPresentationV1=false`；前后端保留运行。页面P0按钮关闭是当前预期配置。
- 受测源码、Runner及JAR指纹见 [最终清单](evidence/auth-feature-20260922/final-manifest.json)。

## 回归结果

| 验证 | 结果 | 原始记录 |
|---|---|---|
| 后端P0整组，含真实Runner、故障、并发 | 615次执行通过，0失败/错误/跳过 | [日志](evidence/auth-feature-20260922/backend-final-regression.log) |
| 最终源码本机MySQL专项 | 32/32通过，无跳过 | [日志](evidence/auth-feature-20260922/mysql-final.log) |
| 旧任务、设备控制、登录数据与算法管理器 | 62/62通过 | [日志](evidence/auth-feature-20260922/legacy-regression.log) |
| 前端 | 32/32通过；生产构建通过 | [测试](evidence/auth-feature-20260922/frontend-final.log)、[构建](evidence/auth-feature-20260922/frontend-build.log) |
| Python协议、容量、自然终态、适配器调用 | 20/20通过 | [日志](evidence/auth-feature-20260922/python-final.log) |
| 最新JAR真实浏览器四动作、STALE、重新同步 | 通过，数据库恰好4条execution，STOP exitCode=0 | [关联ID](evidence/auth-feature-20260922/current-final-summary.json)、[数据库](evidence/auth-feature-20260922/current-final-db.json)、[浏览器](evidence/auth-feature-20260922/current-final-browser/browser-paused.json) |
| 关闭P0后的真实HTTP兼容 | 四动作通过；P0写503；0语音execution；STOP exitCode=0 | [结果](evidence/auth-feature-20260922/legacy-disabled-http.json) |
| 可交付文本和归档脱敏扫描 | 无真实凭据或高置信密钥特征命中 | [扫描](evidence/auth-feature-20260922/secret-scan-final.json) |

自动化数字包含继承和重复并发执行，不等于新增了615条独立要求。独立验收项仍是96条。真实浏览器使用实际Unity应用帧回执，没有伪造成功报告。

## 修复的实际问题

1. **P07**：适配器业务ValueError原会结束Runner；现返回FAILED/ADAPTER_ERROR，协议状态和版本不推进，后续合法命令可继续。不声称回滚适配器内部副作用，不吞掉未知程序异常。
2. **P13**：清理入口在关闭stdin后立即destroy，可打断STOP成功回执后的进程退出。现先等待2秒正常退出，超时才逐级终止。可控退出窗口修复前exit1、修复后exit0，EOF与死锁清理回归通过。历史PID13560日志显示清理先于exit1约18ms，与本次复现路径一致；不是对历史现场的直接重演。
3. **R06**：旧策略版本计划原可确认或发送；现确认和发送前均校验policyVersion并拒绝失效计划。
4. **R04**：无归属旧实例继续拒绝认领；页面补充重新生成场景、运行被占用时由管理员清理的指引。

修复前失败证据保留：[适配器](evidence/auth-feature-20260922/adapter-before-fix.log)、[STOP](evidence/auth-feature-20260922/stop-cleanup-before.json)、[旧策略](evidence/auth-feature-20260922/plan-policy-before.log)。

## 验收口径澄清

- **R02**原用例仅写GENERATION_MISMATCH，而原接口契约也规定确认INVALIDATED提案返回PROPOSAL_INVALIDATED。已区分：仍待确认时发现代次不同返回前者；旧进程结束已使提案失效时返回后者。两条路径均要求409、旧提案失效、新进程零命令，未允许旧提案继续执行。
- **X13**分开验证持久化期限恢复与有效运行的合格迟到展示报告。后端重启后的旧运行LOST，不属于允许补报为就绪的有效实例；未伪造其展示成功。
- **F10**覆盖实际管理器清理、业务服务软删除及记录老化保留。本实现没有专用P0 TTL删除任务，未声称运行过不存在的任务。
- **X07**同Unity实例重新生成场景会递增sceneRevision；新iframe得到新unityInstanceId，revision允许重新起算。这两种情况分别验证。

本报告是本机当前源码的验收结论。团队合并时须使用源码指纹对应修复及脚本；其他机器、不同构建或后续改动需要相应复核。

## 逐项96条清单

详细证据路径保存在 [CSV清单](P0-CASE-COVERAGE-20260922.csv) 和 [本轮分项说明](AUTH-FEATURE-BROWSER-VERIFICATION-20260922.md)。下表不省略任何用例。

| ID | 场景 | 结果 |
|---|---|---|
| X01 | prepare 扩展启用/legacy/失败 | PASS |
| X02 | ready 使用 state；误用 runtimeState | PASS |
| X03 | 参数 short v1 与 JSON long algorithm.command.v1 | PASS |
| X04 | ready/首帧分别接近 60 秒或超时/进程提前退出 | PASS |
| X05 | iframe load 早于 Bridge ready、HELLO 丢失与重试 | PASS |
| X06 | 错 origin、同 origin 错 source、伪造 payload 身份 | PASS |
| X07 | iframe 重载、sceneRevision 增加、旧绑定迟到 | PASS |
| X08 | 场景与帧探测同时触发 | PASS |
| X09 | 同 key 重放报告、新 key 上传旧挑战 | PASS |
| X10 | PAUSED 无新位姿而 Bridge 健康 | PASS |
| X11 | TIMED_OUT/FAILED 申请 FRAME_APPLIED | PASS |
| X12 | 报告帧低于结果帧或高于已接收权威帧 | PASS |
| X13 | E02 成功后 30 秒、重启、迟到合格报告 | PASS |
| X14 | 提案已落库但响应丢失后刷新 | PASS |
| X15 | 确认响应丢失并超过提案有效期 | PASS |
| X16 | 未确认期间上下文变化、恢复日志仍为旧 body | PASS |
| X17 | 用户退出/切换、权限撤销后恢复 | PASS |
| X18 | 功能关闭但执行在途 | PASS |
| X19 | Unity断开、算法仍 SUCCEEDED | PASS |
| X20 | 所有用例仅 FakeRunner 或 Mock 通过 | PASS |
| A01 | 未登录调用所有 P0 端点 | PASS |
| A02 | A 登录但 POST 缺失或错误 CSRF | PASS |
| A03 | C/D 调用提案、确认、取消 | PASS |
| A04 | B 用 R 的 UUID 查询/写入 | PASS |
| A05 | A 直接调用代理后的应用 Service，随后撤销 ADMIN 再调用 | PASS |
| A06 | 请求添加 ownerUserId、runId、executionBackend、requiresConfirmation=false | PASS |
| A07 | body 超过 16 KiB 或 Content-Type 错误 | PASS |
| A08 | 功能关闭请求写接口 | PASS |
| A09 | 撤销权限后重放同 Idempotency-Key | PASS |
| A10 | GET contexts 无本人实例 | PASS |
| R01 | prepare 绑定 A，重复 prepare 同存活进程 | PASS |
| R02 | 替换/重建进程得到 G2，确认 G1 提案 | PASS |
| R03 | B 尝试占用 A 的独立槽位 | PASS |
| R04 | 旧实例没有 owner 元数据 | PASS |
| R05 | 普通 frame sequence 从 25 到 26 | PASS |
| R06 | 确认前成员、能力、策略或状态变化 | PASS |
| R07 | 心跳年龄=5 秒与刚超过 5 秒 | PASS |
| R08 | PAUSED 长时间无新 frame，但心跳持续 | PASS |
| R09 | START/RESUME 场景报告>10秒；PAUSE/STOP 场景报告失效 | PASS |
| R10 | 只有 legacy ready 或不支持目标 action | PASS |
| R11 | 非 P0 域、ROS 执行端、数据库 MissionRun 误当独立实例 | PASS |
| R12 | 每个 action × 每个运行状态参数化 | PASS |
| R13 | algorithmRunId 为不同于 MissionRun 的值或超过 Long 范围 | PASS |
| R14 | 已有未知结果 TIMED_OUT，新提案被确认 | PASS |
| I01 | 创建提案 | PASS |
| I02 | 同用户/operation/键/内容重复创建 | PASS |
| I03 | 同键不同 body 或动作 | PASS |
| I04 | 同键不同用户或不同资源 operation | PASS |
| I05 | I05-a：不受支持的请求版本；I05-b：合法格式但哈希不匹配 | PASS |
| I06 | now 比 expiresAt 小1ms、恰好相等、超过1ms | PASS |
| I07 | 10个并发确认同提案，使用不同键 | PASS |
| I08 | 同一个确认响应丢失，再确认已 CONFIRMED 提案 | PASS |
| I09 | confirm 与 cancel 并发屏障释放 | PASS |
| I10 | 重复 cancel；取消已确认或已失效提案 | PASS |
| I11 | 确认与手动状态操作并发 | PASS |
| I12 | Java/Python 对 fixtures 黄金计划计算哈希 | PASS |
| P01 | 正常 START/PAUSE/RESUME/STOP | PASS |
| P02 | 同 commandId 同内容投递两次 | PASS |
| P03 | 同 commandId 改 action/参数 | PASS |
| P04 | 未知 ID 使用旧/跳跃 commandSequence | PASS |
| P05 | 合法序号但业务状态不合法，再发下一个序号 | PASS |
| P06 | expectedStateVersion 已落后 | PASS |
| P07 | 非法 JSON、未知 action、额外参数、适配器业务异常 | PASS |
| P08 | Java 接收 commandResult 而非 stateChanged | PASS |
| P09 | 错 runtimeRef/代次/来源进程、未知 commandId | PASS |
| P10 | 重复 eventSequence；同序号不同内容 | PASS |
| P11 | SUCCEEDED 后收到旧 ACCEPTED；旧代次迟到 SUCCEEDED | PASS |
| P12 | PAUSE 后没有新 frame | PASS |
| P13 | STOP 最终回执后进程退出；回执前 EOF | PASS |
| P14 | 自然 COMPLETED/FAILED 后发送 RESUME | PASS |
| P15 | result 中 affectedDeviceCodes 与计划不同 | PASS |
| P16 | 连续3个超大/身份违规行、普通 stdout 日志 | PASS |
| P17 | 缓存10000命令后新命令；重复旧命令 | PASS |
| P18 | STATUS_QUERY 查询已知/未知/退出实例 | PASS |
| P19 | PAUSED 心跳持续与 worker 真正死锁 | PASS |
| P20 | Result 与 QueryReply 内层关联 ID 不一致 | PASS |
| F01 | 确认事务提交前异常 | PASS |
| F02 | 确认已提交，worker 还未领取 | PASS |
| F03 | SENDING 持久化后、write前崩溃 | PASS |
| F04 | flush后、SENT提交前崩溃 | PASS |
| F05 | 回执已到但落库失败 | PASS |
| F06 | ACK 5秒/结果15秒边界，模拟快终态无单独ACK | PASS |
| F07 | 超时后迟到可信终态 | PASS |
| F08 | 后端重启/管道所有权丢失 | PASS |
| F09 | outbox READY 10秒未领取 | PASS |
| F10 | 执行处于不确定状态时清理任务运行 | PASS |
| F11 | 单实例两个 worker 同时领取 | PASS |
| F12 | worker发送前撤权/换代/成员变化 | PASS |
| C01 | 功能关闭，运行旧手动算法接口 | PASS |
| C02 | v1实例通过旧手动按钮发动作 | PASS |
| C03 | API 202 QUEUED 返回前端 | PASS |
| C04 | 算法SUCCEEDED但Unity断开/报告过期 | PASS |
| C05 | 换页面/刷新/iframe实例改变后迟到画面报告 | PASS |
| C06 | 两套Unity消息、算法原frame恢复流程 | PASS |
| C07 | 旧任务、设备控制与登录回归 | PASS |
| C08 | 日志/错误/fixture检索 | PASS |
