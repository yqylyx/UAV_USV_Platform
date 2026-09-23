# P0 剩余场景补测结果（2026-09-22）

本轮已补运行中撤权、旧展示身份消息注入、真实后端重启及 STOP 回执前 EOF。**尚未完成全部 96 条验收，不能宣布 P0 完成。**

覆盖统计：PASS 32、PARTIAL 52、NOT_VERIFIED 12、FAIL 0（I05/P17 已修正；P13 退出稳定性待核）。PARTIAL 表示有证据但未覆盖整条要求的所有组合；NOT_VERIFIED 不代表实现必然有缺陷。

## 范围与环境

应用基线：ae46345f1ef22afafddff108f702727fc8bddad3；分支 mxy/p0-local-acceptance-20260922。补测阶段修改测试、取证工具和覆盖文档；I05 后续修正另同步了前端提示与 Mock。后续已接入 2fe4d1e 的 Python 容量修复；生产 Java/Unity 实现未改，本轮后端材料未推送 GitHub。

仅使用本机 uav_usv_p0_integration。测试后前后端保留运行，P0/Unity v1 开关恢复关闭；专用 p0_peer_20260922 恢复 ADMIN 且禁用。没有清空业务库，也没有用伪造的展示报告替代真实正向验收。

## 重点结果

| 场景 | 结果与证据边界 |
|---|---|
| 运行中撤权 | 真实 Runner RUNNING，复用原登录会话；降为 VIEWER/OPERATOR 后提案、确认、取消均 403；禁用后查询也拒绝。同键提案重放无法绕过鉴权。H2 另验证同键确认重放和派发前复检。 |
| 旧 binding/generation | 真实 HTTP 旧绑定返回 CONTEXT_CHANGED，错误代次返回 GENERATION_MISMATCH，未改场景就绪或算法结果。 |
| 浏览器消息注入 | 真实 Edge/WebGL 捕获一条实际待处理报告后，注入错 origin、错 source、错误代次、错误绑定，以及重新绑定后的旧报告，5 项均零对应 HTTP 展示上报。错误代次负例使用随机非当前值；真实旧 Runner 代次另由管道测试覆盖。 |
| 后端真实重启 | Java PID 20612 → 30564；运行 LOST、未确认提案 INVALIDATED；已成功执行结果和画面期限保留，到期 STALE；没有新增执行或回执。实际重启发生于成功状态，不能冒充已发送未知窗口。 |
| STOP 回执前 EOF | 真实 Runner 加测试代理，分别在 ACK 前结束进程、实际 STOP 后丢弃最终 SUCCEEDED；后端 TIMED_OUT/UNKNOWN、运行 LOST，无成功回执，不重发。正常 STOP 成功退出证据沿用前轮。 |
| 并发 | 12 线程确认和 2 线程确认/取消，各完成 100 轮；最多一次执行/写入。此为 H2 与 sender 计数，尚非真实 Runner apply 计数。 |
| 边界 | 36 个动作/状态组合、提案到期前后 1 ms、ACK 5 秒/结果 15 秒、画面帧范围、失败执行门禁、双 worker 领取、回执落库失败恢复等均有逐方法结果。 |

## 补测发现问题与最新处理状态

### P17：容量修复已通过本机独立复验（PASS）

已核对 2fe4d1e，受测 Runner SHA256 与同学完全相同；原指定容量脚本、Python 8 项和 Java 定向回归通过。见 [P17 后端回归报告](P17-BACKEND-REGRESSION-20260922.md)。旧容量失败日志保留历史。

### P13：新增退出稳定性待核（PARTIAL）

首轮 STOP 成功回执后进程 exitCode=1，原测试未断言退出码。补强后 4 轮均为 0，原因未定位，因此单独保留待核，不将其误归为 P17 容量失败。

### I05：契约口径已统一，复测 PASS

保留 Schema 的 expectedPlanVersion const: 1：I05-a 版本 2 返回 400 INVALID_REQUEST；I05-b 版本 1 且合法格式的错误哈希返回 409 PLAN_MISMATCH。确认与取消同规则，均不修改原提案、不创建 execution/outbox、不发送算法命令。

已同步契约、测试设计、样例、前端提示与 Mock，并验证拒绝后不自动重发。新增 HTTP 4 个分支与 service 2 个分支通过；连同现有 HTTP 回归共 14 项通过，前端 28 项通过，生产构建通过。旧失败日志保留为历史，不再作为当前 FAIL。

详见 [I05 修正与前端对接说明](I05-CONTRACT-FIX-20260922.md)。此项通过不代表其他未覆盖场景关闭；P17 已通过；P13 退出稳定性保留待核。

## 结果数量不能混用

- 最新 Java 覆盖批次：388 次执行，0 失败、0 错误、0 跳过。
- 真实 Runner 故障类：38 次执行，其中 32 条为继承基线，6 条为故障实例；新增 STOP EOF 为 2 条。
- 两批归档共 426 次 Java 执行，含继承和重复轮次，不是 426 条独立验收，也不等于 96 条全部通过。
- 真实 Python 协议回归 7/7；真实 HTTP 专项 8 项通过；浏览器负例 5 项通过。
- 6 个 prepare 样例、48 个正负样例、黄金哈希校验通过。
- 早先 P17 独立容量检查 FAIL 为历史；修复后结果见 P17 后端回归报告。

[逐方法索引](evidence/coverage-gaps-20260922/test-method-index.json)；[HTTP 请求与断言](evidence/coverage-gaps-20260922/http-gaps.json)；[浏览器注入记录](evidence/coverage-gaps-20260922/browser-injection.json)；[重启前数据库](evidence/coverage-gaps-20260922/db-before-restart.json)；[重启后数据库](evidence/coverage-gaps-20260922/db-after-restart.json)；[最终数据库](evidence/coverage-gaps-20260922/db-final.json)。原始日志、Surefire XML、管道 JSONL 和截图同目录保存。

## HTTP 重启轮关联身份

- runtimeRef：3a16cf26-495c-4872-85c0-a602ab60990c
- runtimeGeneration：4641b793-5e8f-4c06-bdf6-954197568ed4
- runId：1790077613146
- START executionId：558c3951-984e-4262-bf0e-fcc3fea01a6b
- commandId：160596ce-b305-407e-8ab4-fc445494dc3b
- 重启前未确认 proposalId：aad0fca4-3db5-4878-866c-d0a673808cc8
- 原展示期限：2026-09-22T11:47:25.538759Z（UTC），重启未延长。

## 复用方式

Java 选择 VoiceCoverageGapTests、VoiceHttpTests、VoiceProcessTests、VoiceDeviceMembershipTests。真实故障类另设置 P0_REAL_RUNNER 和 PYTHON_COMMAND，再运行 VoiceRealRunnerFaultTests。本轮没有重复成员四的 MySQL 专项 32 项测试。

真实 HTTP 工具使用 requests，传入本机凭据文件、专用测试账号、MySQL 程序、独立输出目录和重启脚本。专用账号必须以 p0_peer_ 开头，finally 恢复角色及 enabled；账号密码不写入证据。

通用重启工具 restart-isolated-backend-for-test.ps1 需要 P0_WORKSPACE、P0_ISOLATED_LOCAL_DIR、P0_GAP_EVIDENCE_DIR。只重启 runtime.json 记录且命令行身份匹配的隔离 Java。每次使用新证据目录，并为 --powershell 指定可用 pwsh.exe。

```powershell
python test-http-coverage-gaps.py --credentials <凭据文件> --peer <专用账号文件> --mysql <mysql.exe> --output <新证据目录> --restart-script <重启脚本> --powershell <pwsh.exe>
python test-runner-capacity.py --runner <runner.py> --output <新证据目录/runner-capacity.json>
```

首次 HTTP 导出因表主键列名错误失败，修为 id 后重试；第二次 Windows PowerShell 子进程输出等待中断，账号恢复后改用 pwsh 和不继承输出管道，最终整轮通过。失败尝试保留，不冒充应用缺陷或通过证据。matrix-initial-assertions.log 中 sender 将只读查询误判为算法写入的测试断言已修正；I05 契约差异保留历史记录，现已统一并通过补充回归。

## 下一轮团队分工

- Python：P17 已通过；配合排查 P13 退出稳定性，补自然终态 P14、动作处理真阻塞 P19及真实 apply 计数。
- 后端：I05 已完成；继续补真实 write/flush 崩溃窗口、落库故障期间其他实例禁止派发、已发送未知状态下实际 Java 重启。
- 前端/Unity：补 iframe 真重载/sceneRevision、撤权后页面恢复和旧用户消息、场景/帧探测并发、真实 Unity 断连显示。
- 测试：按下表逐项补证；H2、真实进程、HTTP、WebGL 分开记录，避免重复已通过方法。未关闭项不能用同类用例替代。

## 完整 96 条逐项清单

机器可读版本：[P0-CASE-COVERAGE-20260922.csv](P0-CASE-COVERAGE-20260922.csv)。

| ID | 场景 | 状态 | 证据或候选 | 覆盖边界/后续 |
|---|---|---|---|---|
| X01 | prepare 扩展启用/legacy/失败 | PARTIAL | VoiceProcessTests; VoiceRealRunnerTests; HTTP-EVIDENCE-20260922.md | 真实正常 prepare 已通过；重复准备/能力子集/legacy/失败/60秒边界不得由正常路径代替。 |
| X02 | ready 使用 state；误用 runtimeState | PARTIAL | VoiceProcessTests; VoiceRealRunnerTests; HTTP-EVIDENCE-20260922.md | 真实正常 prepare 已通过；重复准备/能力子集/legacy/失败/60秒边界不得由正常路径代替。 |
| X03 | 参数 short v1 与 JSON long algorithm.command.v1 | PARTIAL | VoiceProcessTests; VoiceRealRunnerTests; HTTP-EVIDENCE-20260922.md | 真实正常 prepare 已通过；重复准备/能力子集/legacy/失败/60秒边界不得由正常路径代替。 |
| X04 | ready/首帧分别接近 60 秒或超时/进程提前退出 | PARTIAL | VoiceProcessTests; VoiceRealRunnerTests; HTTP-EVIDENCE-20260922.md | 真实正常 prepare 已通过；重复准备/能力子集/legacy/失败/60秒边界不得由正常路径代替。 |
| X05 | iframe load 早于 Bridge ready、HELLO 丢失与重试 | PARTIAL | HANDOFF-20260922.md; HTTP-EVIDENCE-20260922.md; INTEGRATED-DUAL-ACCOUNT-ACCEPTANCE-20260922.md | 真实浏览器与 Unity 展示链路现已就绪；本轮正常握手/恢复不能替代本用例指定的故障注入或完整边界检查，仍须逐项补证。 |
| X06 | 错 origin、同 origin 错 source、伪造 payload 身份 | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/browser-injection.json | 真实 Edge/WebGL：对捕获的真实待处理报告注入错 origin、错 source、错误 binding/generation，4 项均零对应 HTTP 上报。 |
| X07 | iframe 重载、sceneRevision 增加、旧绑定迟到 | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/browser-injection.json; http-gaps.json | 真实重新绑定后的旧报告零 HTTP 上报、HTTP 旧绑定返回 CONTEXT_CHANGED；仍需 iframe 真重载及 sceneRevision 递增组合，不能由重新绑定替代。 |
| X08 | 场景与帧探测同时触发 | NOT_VERIFIED | HANDOFF-20260922.md; HTTP-EVIDENCE-20260922.md; INTEGRATED-DUAL-ACCOUNT-ACCEPTANCE-20260922.md | 真实浏览器与 Unity 展示链路现已就绪；本轮正常握手/恢复不能替代本用例指定的故障注入或完整边界检查，仍须逐项补证。 |
| X09 | 同 key 重放报告、新 key 上传旧挑战 | PARTIAL | VoiceControlTests.presentationBindingEvidenceExpiresAndReplayCannotRefresh | 后端挑战模拟测试候选；真实浏览器不续期现场证据待补。 |
| X10 | PAUSED 无新位姿而 Bridge 健康 | PARTIAL | HANDOFF-20260922.md; HTTP-EVIDENCE-20260922.md; INTEGRATED-DUAL-ACCOUNT-ACCEPTANCE-20260922.md | 真实浏览器与 Unity 展示链路现已就绪；本轮正常握手/恢复不能替代本用例指定的故障注入或完整边界检查，仍须逐项补证。 |
| X11 | TIMED_OUT/FAILED 申请 FRAME_APPLIED | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#unsuccessfulExecutionCannotAcquireFrameChallenge | H2/service 参数化：TIMED_OUT/FAILED/REJECTED/INVALIDATED 均拒绝帧挑战，执行状态保持；不是伪造的真实 Unity 验收。 |
| X12 | 报告帧低于结果帧或高于已接收权威帧 | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#presentationFrameBounds | H2/service：结果帧 3、权威最新帧 5；帧 2/6 拒绝，3/5 接受，算法成功与命令次数不变。 |
| X13 | E02 成功后 30 秒、重启、迟到合格报告 | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/http-gaps.json; db-before-restart.json; db-final.json | 实际 Java PID 更换后成功结果和原 30 秒期限保留并到期 STALE；迟到合格报告只有 service 夹具证据，实际旧运行 LOST 后不得伪造报告恢复。 |
| X14 | 提案已落库但响应丢失后刷新 | PARTIAL | 前端恢复实现及成员四汇总记录 | 需补真实浏览器逐项证据，可先独立检查受理文案、请求日志和用户切换清理；不应一律等待 Unity。 |
| X15 | 确认响应丢失并超过提案有效期 | PASS | VoiceControlTests.confirmedReplaySurvivesExpiry; INTEGRATED-DUAL-ACCOUNT-ACCEPTANCE-20260922.md | 确认响应丢失且提案过期后，通过权威查询恢复同一 execution；原幂等记录存在，无第二次确认 POST 或算法动作。 |
| X16 | 未确认期间上下文变化、恢复日志仍为旧 body | PARTIAL | 前端恢复实现及成员四汇总记录 | 需补真实浏览器逐项证据，可先独立检查受理文案、请求日志和用户切换清理；不应一律等待 Unity。 |
| X17 | 用户退出/切换、权限撤销后恢复 | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/http-gaps.json; browser-injection.json | 真实会话运行中降为 VIEWER/OPERATOR 与禁用账号均拒绝；前轮 A→B→A 通过。撤权后页面恢复/旧用户消息的完整浏览器组合仍待补。 |
| X18 | 功能关闭但执行在途 | PARTIAL | VoiceControlTests.disableStopsNewWritesButDrainsAcceptedExecution | 需补功能开关与在途对账的分项证据；重启行为单独验收。 |
| X19 | Unity断开、算法仍 SUCCEEDED | NOT_VERIFIED | HANDOFF-20260922.md; HTTP-EVIDENCE-20260922.md; INTEGRATED-DUAL-ACCOUNT-ACCEPTANCE-20260922.md | 真实浏览器与 Unity 展示链路现已就绪；本轮正常握手/恢复不能替代本用例指定的故障注入或完整边界检查，仍须逐项补证。 |
| X20 | 所有用例仅 FakeRunner 或 Mock 通过 | NOT_VERIFIED | HANDOFF-20260922.md; HTTP-EVIDENCE-20260922.md; INTEGRATED-DUAL-ACCOUNT-ACCEPTANCE-20260922.md | 真实浏览器与 Unity 展示链路现已就绪；本轮正常握手/恢复不能替代本用例指定的故障注入或完整边界检查，仍须逐项补证。 |
| A01 | 未登录调用所有 P0 端点 | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceHttpTests.xml#allEndpointsDenyAnonymousAndAllPostsRequireCsrf | MockMvc：5 个 GET、6 个 POST 未登录均 401；6 个 POST 缺失/错误 CSRF 共 12 组合均 403 CSRF_INVALID；零提案/执行。 |
| A02 | A 登录但 POST 缺失或错误 CSRF | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceHttpTests.xml#allEndpointsDenyAnonymousAndAllPostsRequireCsrf | MockMvc：5 个 GET、6 个 POST 未登录均 401；6 个 POST 缺失/错误 CSRF 共 12 组合均 403 CSRF_INVALID；零提案/执行。 |
| A03 | C/D 调用提案、确认、取消 | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceHttpTests.xml#bothNonAdminRolesDenyEveryCommandWrite; http-gaps.json | VIEWER/OPERATOR × 提案/确认/取消均 403；实际运行中复用原 ADMIN 会话撤权也被拒绝。 |
| A04 | B 用 R 的 UUID 查询/写入 | PARTIAL | VoiceControlTests.crossOwnerNotFoundAndServiceRoleRechecked | 候选后端测试已存在；补齐直接 Service、撤权、跨用户读写的逐项结果。 |
| A05 | A 直接调用代理后的应用 Service，随后撤销 ADMIN 再调用 | PARTIAL | VoiceControlTests.crossOwnerNotFoundAndServiceRoleRechecked | 候选后端测试已存在；补齐直接 Service、撤权、跨用户读写的逐项结果。 |
| A06 | 请求添加 ownerUserId、runId、executionBackend、requiresConfirmation=false | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#dangerousUnknownProposalFieldsAreRejected | 4 个额外字段分别测试 INVALID_REQUEST，零提案/执行/管道写入。 |
| A07 | body 超过 16 KiB 或 Content-Type 错误 | PARTIAL | VoiceHttpTests | 已有 HTTP 自动化汇总；需逐端点/角色关联精确方法及原始结果，不能将类级通过当作全组合覆盖。 |
| A08 | 功能关闭请求写接口 | PARTIAL | VoiceControlTests.disableStopsNewWritesButDrainsAcceptedExecution | 需补功能开关与在途对账的分项证据；重启行为单独验收。 |
| A09 | 撤销权限后重放同 Idempotency-Key | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#revocationRejectsCachedConfirmationAndNewWrites; http-gaps.json | 3 种撤权状态下同键确认重放拒绝；真实 HTTP 同键提案缓存重放拒绝；发送前复检使已排队执行失效。 |
| A10 | GET contexts 无本人实例 | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceHttpTests.xml#readHasNoStoreAndNoInstancesIsEmpty | MockMvc：无本人实例返回 200 和空数组，Cache-Control=no-store；无自动 prepare。 |
| R01 | prepare 绑定 A，重复 prepare 同存活进程 | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceProcessTests.xml#existingManagerNegotiatesPipesAndSerializesFourManualActions | Java 管理真实子进程夹具：重复 prepare 保持 ref/generation；进程夹具不等同生产 Python adapter，但本项生命周期断言已执行。 |
| R02 | 替换/重建进程得到 G2，确认 G1 提案 | PARTIAL | VoiceRealRunnerFaultTests.restartRejectsOldGenerationCommandAndReceipt; RUNNER-FAULTS-20260922.md | 旧回执/旧帧/旧命令的真实检查通过；仍需旧提案确认、旧执行对账及乱序组合证据。协议错误后的通道保护符合契约。 |
| R03 | B 尝试占用 A 的独立槽位 | PARTIAL | VoiceProcessTests; VoiceRealRunnerTests; HTTP-EVIDENCE-20260922.md | 真实正常 prepare 已通过；重复准备/能力子集/legacy/失败/60秒边界不得由正常路径代替。 |
| R04 | 旧实例没有 owner 元数据 | NOT_VERIFIED | 尚未完成精确测试方法与证据映射 | 未逐项核验，不代表一定未实现；先检查已有测试和成员四证据，再决定是否补测，避免重复。 |
| R05 | 普通 frame sequence 从 25 到 26 | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#ordinaryFramesDoNotInvalidatePlan | H2/service：普通帧递增且成员相同后原提案仍能确认。 |
| R06 | 确认前成员、能力、策略或状态变化 | PARTIAL | VoiceControlTests.changedContextInvalidatesFrozenPlan | 需逐一覆盖成员、能力、策略和状态变化，不能只证明一种上下文变化。 |
| R07 | 心跳年龄=5 秒与刚超过 5 秒 | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#heartbeatBoundaryAndPauseDoesNotNeedScene; java-real-faults.log | 固定单调钟精确 5000/5001 ms + 真实 Runner 心跳截断均已归档。 |
| R08 | PAUSED 长时间无新 frame，但心跳持续 | PARTIAL | VoiceRealRunnerTests; HTTP-EVIDENCE-20260922.md | 暂停心跳及四动作已通过；长期无新帧/帧号保持等精确断言需补证。 |
| R09 | START/RESUME 场景报告>10秒；PAUSE/STOP 场景报告失效 | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#staleSceneGatesOnlyStartAndResume | 4 动作均独立测试，场景年龄 10001 ms、心跳新鲜：仅 START/RESUME 被门禁拒绝。 |
| R10 | 只有 legacy ready 或不支持目标 action | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#unsupportedProtocolOrActionNeverWrites | legacy 与目标能力缺失分别返回 PROTOCOL_UNSUPPORTED/UNSUPPORTED_CAPABILITY，零执行/写入。 |
| R11 | 非 P0 域、ROS 执行端、数据库 MissionRun 误当独立实例 | NOT_VERIFIED | 尚未完成精确测试方法与证据映射 | 未逐项核验，不代表一定未实现；先检查已有测试和成员四证据，再决定是否补测，避免重复。 |
| R12 | 每个 action × 每个运行状态参数化 | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#actionStateMatrix | H2/service：4 动作 × 9 状态，共 36 组合。包含 8 个协议运行状态及 LOST；检查合法动作表，不代表 36 个真实算法生命周期。 |
| R13 | algorithmRunId 为不同于 MissionRun 的值或超过 Long 范围 | NOT_VERIFIED | 尚未完成精确测试方法与证据映射 | 未逐项核验，不代表一定未实现；先检查已有测试和成员四证据，再决定是否补测，避免重复。 |
| R14 | 已有未知结果 TIMED_OUT，新提案被确认 | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#timeoutRemainsUnknownOccupiedAndLateSuccessReconciles | 未知结果超时后新确认返回 EXECUTION_IN_PROGRESS，可信迟到成功可对账且不重发。 |
| I01 | 创建提案 | PARTIAL | VoiceControlTests.happyPathAndPublicShapes | 真实浏览器正常链路已通过；本项逐步骤 201/200、资源计数和到期时间不变的完整断言仍需单列，已不被 Unity 就绪阻断。 |
| I02 | 同用户/operation/键/内容重复创建 | PARTIAL | VoiceControlTests.happyPathAndPublicShapes | 真实浏览器正常链路已通过；本项逐步骤 201/200、资源计数和到期时间不变的完整断言仍需单列，已不被 Unity 就绪阻断。 |
| I03 | 同键不同 body 或动作 | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#sameKeyDifferentBodyRejectedBeforeAnyExecution | H2/service：同键改动作被 IDEMPOTENCY_CONFLICT 拒绝；仍只有 1 提案、0 执行。 |
| I04 | 同键不同用户或不同资源 operation | NOT_VERIFIED | 尚未完成精确测试方法与证据映射 | 未逐项核验，不代表一定未实现；先检查已有测试和成员四证据，再决定是否补测，避免重复。 |
| I05 | I05-a：不受支持的请求版本；I05-b：合法格式但哈希不匹配 | PASS | I05-CONTRACT-FIX-20260922.md; evidence/i05-contract-20260922/TEST-VoiceHttpTests.xml#i05SchemaAndPlanErrorsHaveNoSideEffects; evidence/i05-contract-20260922/TEST-VoiceCoverageGapTests.xml#wrongPlanNeverCreatesExecution | 已按现行 Schema const=1 统一契约。确认/取消 4 个 HTTP 分支、2 个 service 分支通过；前端提示、Mock 和拒绝后不自动重发通过。非真实浏览器重跑。 |
| I06 | now 比 expiresAt 小1ms、恰好相等、超过1ms | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#proposalExpiryAtEachMillisecondBoundary | 固定时钟 29999/30000/30001 ms：前者可确认，后两者 PROPOSAL_EXPIRED 并持久化 EXPIRED。 |
| I07 | 10个并发确认同提案，使用不同键 | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#confirmConcurrencyHundredRounds/confirmCancelHundredRounds | 分别 100 轮 H2 并发已通过：确认 12 线程，确认/取消 2 线程；每轮最多 1 执行与写入。仍缺真实 Runner apply 计数，不能把 H2 写入计数说成真实 apply。 |
| I08 | 同一个确认响应丢失，再确认已 CONFIRMED 提案 | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#confirmedReplaySurvivesExpiry; INTEGRATED-DUAL-ACCOUNT-ACCEPTANCE-20260922.md | Service 到期后确认重放保持同执行；前轮真实浏览器确认响应丢失用 GET 恢复，未做第二次 confirm POST，不能混称。 |
| I09 | confirm 与 cancel 并发屏障释放 | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#confirmConcurrencyHundredRounds/confirmCancelHundredRounds | 分别 100 轮 H2 并发已通过：确认 12 线程，确认/取消 2 线程；每轮最多 1 执行与写入。仍缺真实 Runner apply 计数，不能把 H2 写入计数说成真实 apply。 |
| I10 | 重复 cancel；取消已确认或已失效提案 | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#duplicateCancelAndConfirmedCancelNeverWrite | 同 key/新 key 重复取消与取消已确认提案通过；取消失效/过期提案的独立结果仍待补。 |
| I11 | 确认与手动状态操作并发 | NOT_VERIFIED | 尚未完成精确测试方法与证据映射 | 未逐项核验，不代表一定未实现；先检查已有测试和成员四证据，再决定是否补测，避免重复。 |
| I12 | Java/Python 对 fixtures 黄金计划计算哈希 | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/contracts.log; TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#frozenGoldenHashAndAllSchemaFixtures | Java/Python 黄金哈希、48 正负例及 6 prepare 样例通过；设备输入顺序变化的独立计划构造断言待补。 |
| P01 | 正常 START/PAUSE/RESUME/STOP | PASS | evidence/http-runner-20260922.json; evidence/java-python-062aadd-20260922.json; INTEGRATED-DUAL-ACCOUNT-ACCEPTANCE-20260922.md | 本机真实 P0 四动作、数据库关联与真实展示回执通过。 |
| P02 | 同 commandId 同内容投递两次 | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/python-protocol.log | 复用真实 Runner 7 项测试：重复缓存、改 action 冲突、跳号、版本不匹配、坏 JSON/数字/协议通过；尚缺 apply 直接计数、改参数、旧序号、落后版本、适配器业务异常等对应组合。 |
| P03 | 同 commandId 改 action/参数 | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/python-protocol.log | 复用真实 Runner 7 项测试：重复缓存、改 action 冲突、跳号、版本不匹配、坏 JSON/数字/协议通过；尚缺 apply 直接计数、改参数、旧序号、落后版本、适配器业务异常等对应组合。 |
| P04 | 未知 ID 使用旧/跳跃 commandSequence | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/python-protocol.log | 复用真实 Runner 7 项测试：重复缓存、改 action 冲突、跳号、版本不匹配、坏 JSON/数字/协议通过；尚缺 apply 直接计数、改参数、旧序号、落后版本、适配器业务异常等对应组合。 |
| P05 | 合法序号但业务状态不合法，再发下一个序号 | NOT_VERIFIED | 尚未完成精确测试方法与证据映射 | 未逐项核验，不代表一定未实现；先检查已有测试和成员四证据，再决定是否补测，避免重复。 |
| P06 | expectedStateVersion 已落后 | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/python-protocol.log | 复用真实 Runner 7 项测试：重复缓存、改 action 冲突、跳号、版本不匹配、坏 JSON/数字/协议通过；尚缺 apply 直接计数、改参数、旧序号、落后版本、适配器业务异常等对应组合。 |
| P07 | 非法 JSON、未知 action、额外参数、适配器业务异常 | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/python-protocol.log | 复用真实 Runner 7 项测试：重复缓存、改 action 冲突、跳号、版本不匹配、坏 JSON/数字/协议通过；尚缺 apply 直接计数、改参数、旧序号、落后版本、适配器业务异常等对应组合。 |
| P08 | Java 接收 commandResult 而非 stateChanged | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#stateChangedFrameAndHttpReceiptNeverProveSuccess | 帧/心跳状态变化不结算 execution；只读展示证据不能替代关联算法回执。 |
| P09 | 错 runtimeRef/代次/来源进程、未知 commandId | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/java-real-faults.log; TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#lateAcceptedNeverRollsBackSuccess | 旧代次真实回执/帧/命令注入与 SUCCEEDED 后旧 ACCEPTED 不回退通过；旧执行对账与新代次并存的全组合仍待补。 |
| P10 | 重复 eventSequence；同序号不同内容 | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#conflictingDuplicateDoesNotOverwriteSuccessfulResult; java-real-faults.log | 重复迟到回执去重；同 eventSequence 不同内容不覆盖成功，通道进入保护状态。 |
| P11 | SUCCEEDED 后收到旧 ACCEPTED；旧代次迟到 SUCCEEDED | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/java-real-faults.log; TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#lateAcceptedNeverRollsBackSuccess | 旧代次真实回执/帧/命令注入与 SUCCEEDED 后旧 ACCEPTED 不回退通过；旧执行对账与新代次并存的全组合仍待补。 |
| P12 | PAUSE 后没有新 frame | PARTIAL | VoiceRealRunnerTests; HTTP-EVIDENCE-20260922.md | 暂停心跳及四动作已通过；长期无新帧/帧号保持等精确断言需补证。 |
| P13 | STOP 最终回执后进程退出；回执前 EOF | PARTIAL | P17-BACKEND-REGRESSION-20260922.md; evidence/p17-backend-2fe4d1e-20260922/java-regression.log; strengthened-java-four-actions.json; stop-exit-repeat-1.json; stop-exit-repeat-2.json; stop-exit-repeat-3.json | STOP 最终回执和回执前 EOF 均已验证；本轮首次正常 STOP 后日志退出码 1，旧测试未断言退出码。加严后 4 轮均为 0，但首次原因未定位，保守保留退出稳定性待核。不是 P17 容量失败。 |
| P14 | 自然 COMPLETED/FAILED 后发送 RESUME | NOT_VERIFIED | algorithm-service/runner.py | 静态疑点待专项动态验证：非法输入异常处理/自然终态/10000缓存上限；不得预先记为动态FAIL或PASS。 |
| P15 | result 中 affectedDeviceCodes 与计划不同 | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceDeviceMembershipTests.xml; TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#mismatchedMembersCannotSettleExecution | 空回执成员/不匹配成员均不结算成功，不扩大设备集合；规范 deviceCode 正例通过。 |
| P16 | 连续3个超大/身份违规行、普通 stdout 日志 | PARTIAL | VoiceControlTests.boundedLineReaderDrainsOversizedLine; threeInvalidEnvelopesMakeChannelReadOnlyWithoutChangingState | 需核对连续超大/身份违规及普通 stdout 日志的完整组合证据。 |
| P17 | 缓存10000命令后新命令；重复旧命令 | PASS | P17-BACKEND-REGRESSION-20260922.md; evidence/p17-backend-2fe4d1e-20260922/local-runner-capacity.json; python-tests.log; initial-TEST-VoiceCoverageGapTests.xml | 已核对远端 2fe4d1e 与附件源码（仅 CRLF 差异）；原指定脚本本机通过，Python 8/8、Java 定向 9/9。容量错误不会结算成功或自动重发。P13 非零退出观察独立保留。 |
| P18 | STATUS_QUERY 查询已知/未知/退出实例 | PARTIAL | VoiceControlTests.queryUnknownNeverResendsAndMaxThreeQueries; RUNNER-FAULTS-20260922.md | 真实已知结果查询恢复通过；未知/退出与嵌套错误ID的真实负例仍需补充。 |
| P19 | PAUSED 心跳持续与 worker 真正死锁 | PARTIAL | RUNNER-FAULTS-20260922.md | 心跳截断测试不是 worker 真死锁；还需动作应用线程卡死的测试。 |
| P20 | Result 与 QueryReply 内层关联 ID 不一致 | PARTIAL | VoiceControlTests.queryUnknownNeverResendsAndMaxThreeQueries; RUNNER-FAULTS-20260922.md | 真实已知结果查询恢复通过；未知/退出与嵌套错误ID的真实负例仍需补充。 |
| F01 | 确认事务提交前异常 | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#transactionFailureRollsBackProposalExecutionAndOutbox | 确认事务内制造数据库异常：提案仍待确认，execution/outbox 全回滚。 |
| F02 | 确认已提交，worker 还未领取 | NOT_VERIFIED | 尚未完成精确测试方法与证据映射 | 未逐项核验，不代表一定未实现；先检查已有测试和成员四证据，再决定是否补测，避免重复。 |
| F03 | SENDING 持久化后、write前崩溃 | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#committedSendingFailureDoesNotRetry | 已在 SENDING 提交后、sender 写入前/后注入异常，UNCERTAIN/UNKNOWN 且不重发；这是内存 sender 边界夹具，真实 OS flush 与进程崩溃窗口仍待屏障取证。 |
| F04 | flush后、SENT提交前崩溃 | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#committedSendingFailureDoesNotRetry | 已在 SENDING 提交后、sender 写入前/后注入异常，UNCERTAIN/UNKNOWN 且不重发；这是内存 sender 边界夹具，真实 OS flush 与进程崩溃窗口仍待屏障取证。 |
| F05 | 回执已到但落库失败 | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#receiptPersistenceFailureIsBufferedAndReconciled | H2 使回执表暂时不可用：不报成功、恢复后缓冲回执落库且不重发；仍缺另一实例排队命令在故障期间禁止发送的证明。 |
| F06 | ACK 5秒/结果15秒边界，模拟快终态无单独ACK | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#exactCommandTimeoutBoundary/presentationFrameBounds | 固定单调钟 ACK 4999/5000 ms、结果 14999/15000 ms；可信最终回执可无单独 ACK 完成，迟到仍保留 timedOutAt。 |
| F07 | 超时后迟到可信终态 | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/java-real-faults.log; TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#timeoutRemainsUnknownOccupiedAndLateSuccessReconciles | 真实查询恢复和 service 迟到结算均保留超时事实、只写 1 次算法命令。 |
| F08 | 后端重启/管道所有权丢失 | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/http-gaps.json; restart.json; TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#restartRecoversEachDispatchStageWithoutReplay | 真实 Java 重启：LOST、未确认失效、成功及期限保留、零重放；QUEUED/DISPATCHED/ACCEPTED/SUCCEEDED 分阶段恢复已有 H2 证据。实际进程重启发生于已发送未知窗口仍待补。 |
| F09 | outbox READY 10秒未领取 | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#queueExpiryDoesNotSendOrConsumeCommandSequence | 固定时钟队列恰好 10 秒过期：DISPATCH_DEADLINE_EXCEEDED，零写入、不消费命令序号。 |
| F10 | 执行处于不确定状态时清理任务运行 | NOT_VERIFIED | 尚未完成精确测试方法与证据映射 | 未逐项核验，不代表一定未实现；先检查已有测试和成员四证据，再决定是否补测，避免重复。 |
| F11 | 单实例两个 worker 同时领取 | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#twoWorkersOnlyClaimOneOutbox | 同实例两个不同 Dispatcher 屏障并发领取，1 outbox、1 次写入；H2 事务测试。 |
| F12 | worker发送前撤权/换代/成员变化 | PASS | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/TEST-com.uavusv.platform.module.voicecontrol.VoiceCoverageGapTests.xml#dispatchRechecksChangedIdentityAndMembership/revocationRejectsCachedConfirmationAndNewWrites | 发送前撤权、换代、成员变化分别使执行 INVALIDATED，零管道写入。 |
| C01 | 功能关闭，运行旧手动算法接口 | PARTIAL | 团队既有兼容回归反馈; HTTP-EVIDENCE-20260922.md | 本轮 HTTP 四动作在开关开启时验证；关闭模式及旧任务/设备链路完整回归不可据此宣称通过。 |
| C02 | v1实例通过旧手动按钮发动作 | PASS | evidence/http-runner-20260922.json; evidence/http-readonly-20260922.tsv | 真实旧手动HTTP入口进入MANUAL提案/执行与同一调度器，有ID及回执关联。 |
| C03 | API 202 QUEUED 返回前端 | PARTIAL | 前端恢复实现及成员四汇总记录 | 需补真实浏览器逐项证据，可先独立检查受理文案、请求日志和用户切换清理；不应一律等待 Unity。 |
| C04 | 算法SUCCEEDED但Unity断开/报告过期 | PARTIAL | HANDOFF-20260922.md; HTTP-EVIDENCE-20260922.md; INTEGRATED-DUAL-ACCOUNT-ACCEPTANCE-20260922.md | 真实断报→STALE→重新同步展示通过；完整 Unity 断连变体仍待验收。 |
| C05 | 换页面/刷新/iframe实例改变后迟到画面报告 | PARTIAL | REMAINING-CASE-ACCEPTANCE-20260922.md; evidence/coverage-gaps-20260922/browser-injection.json; http-gaps.json | 真实重新绑定后的旧报告零 HTTP 上报、HTTP 旧绑定返回 CONTEXT_CHANGED；仍需 iframe 真重载及 sceneRevision 递增组合，不能由重新绑定替代。 |
| C06 | 两套Unity消息、算法原frame恢复流程 | PARTIAL | HANDOFF-20260922.md; HTTP-EVIDENCE-20260922.md; INTEGRATED-DUAL-ACCOUNT-ACCEPTANCE-20260922.md | 真实 WebGL 恢复且同运行 prepare 一次；所有位姿坐标协议兼容组合仍需单列验证。 |
| C07 | 旧任务、设备控制与登录回归 | PARTIAL | 团队既有兼容回归反馈; HTTP-EVIDENCE-20260922.md | 本轮 HTTP 四动作在开关开启时验证；关闭模式及旧任务/设备链路完整回归不可据此宣称通过。 |
| C08 | 日志/错误/fixture检索 | PARTIAL | HTTP-EVIDENCE-20260922.md | 已上传8个文件执行过真实凭据值扫描；全项目日志/错误/fixture 的完整扫描仍待映射。 |
