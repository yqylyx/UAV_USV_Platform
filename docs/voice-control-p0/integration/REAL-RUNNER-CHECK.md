# Java—Python 可重复联调（后端负责）

## 边界

这些工具只新增后端测试和脚本，不修改 algorithm-service 或 Unity。Python 同学继续负责 deviceCode 和 affectedDeviceCodes 修复。

测试使用真实 AlgorithmRuntimeManager、VoiceRuntimeBridge、命令队列和回执校验，通过标准输入输出启动指定 Python Runner。数据库为每次新建的内存 H2；账号和配置只用于测试。不访问 MySQL，不需要登录凭据，不改变正在运行的前后端及其功能开关。

这是进程级 Java—Python 集成检查，不是 HTTP、浏览器、提案确认或 Unity 联合验收。目录中的 contract_runner.py 只能作工具自测，不能作为真实算法通过的证据。

## 先运行设备名单回归

在仓库根目录执行（需要 Java 21、Maven）：

```powershell
mvn.cmd -f backend/pom.xml '-Dtest=VoiceDeviceMembershipTests#codeOnlyRealFrameRejectsActionWithoutEnqueueing+canonicalDeviceCodesBecomeTheExactCommandMembership+emptySuccessfulReceiptCannotSettleOrAdvanceRuntime' test
```

三项新增回归：

1. 来自真实 0577987 算法帧的 code-only 数据必须被拒绝，不能创建 execution。
2. 显式补齐 deviceCode 后，命令设备集合必须与六个真实帧成员完全一致。这里是契约正向用例，不代表 Python 已修复。
3. 空 affectedDeviceCodes 的成功回执不能将 execution 或运行状态推进为成功。

捕获帧：backend/src/test/resources/voicecontrol/real-adapter-code-frame.json；来源为 2026-09-21 本机 runId=990022 的 prepare.latestFrame，无凭据。

## 指定 Python 同学的真实 Runner

先取得同学修复后的完整 algorithm-service 目录和对应依赖。不能只复制 runner.py，因为它需要同目录模块及算法资源。脚本不会自动拉取、切换、合并或修改同学分支。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\docs\voice-control-p0\integration\test-real-runner.ps1 -Runner 'C:\path\to\algorithm-service\runner.py' -Python 'D:\soteware\anaconda\python.exe' -Maven 'D:\soteware\apache-maven-3.9.6\bin\mvn.cmd' -JavaHome 'C:\Program Files\Java\jdk-21'
```

ExecutionPolicy Bypass 仅用于本次 PowerShell 进程，不修改系统策略。请替换 Runner 为本机真实路径；Runner 所属 Python 环境须预先具备算法依赖。

脚本打印 Runner 路径及 SHA256，显式执行唯一的真实联调用例。它不会将条件未启用的跳过结果当作成功。启动失败、心跳缺失、设备字段缺失、错误回执、动作超时或 STOP 不退出都会返回失败。每次运行使用新内存数据库，结束通过 manager.close 回收该测试创建的进程；不要并发执行多个 Maven 测试写同一 target 目录。

## 自动核对内容

- prepare 的 PREPARED、v1 协议、四动作能力及 UUID 运行身份；初始帧设备名单非空且字段合法。
- 首次心跳，以及 PAUSE 后心跳序号继续增长。
- START → PAUSE → RESUME → STOP 顺序执行，不借用 Unity 假回执。
- 各 execution 达到 SUCCEEDED/SUCCESS，包含 ACCEPTED 和 SUCCEEDED 回执。
- commandId 唯一且回执对应正确；runtimeRef、runtimeGeneration、设备名单、状态版本及目标状态正确。
- STOP 成功回执后 Runner 退出。

每步动作等待上限 10 秒；prepare 使用生产进程管理器自身启动超时。

## 查看证据

- backend/target/p0-real-runner-report.json：prepare、心跳上下文、四动作执行记录及回执，或具体失败原因。
- backend/target/surefire-reports：JUnit 结果。

每次运行会清除旧 JSON，避免编译失败时误读历史 PASS。新报告会覆盖旧报告；保留证据时请另存，并同时记录后端和 Python 提交号、Runner SHA256。启动之前的路径/依赖错误或编译失败可能没有新 JSON，此时以脚本失败和 Maven 输出为准。

## 当前验收规则

三项后端回归通过不表示 Python 已修复。0577987 的真实设备帧缺少 deviceCode，真实集成检查应失败；Python 修复后重新执行，四动作全部通过才进入 Unity 展示联调。

## 2026-09-21 本机执行结果

- 新增设备名单回归：3/3 通过，无跳过。
- 真实 Runner 0577987：失败，明确定位 `Real adapter frame missing valid deviceCode; legacy code=UAV-001`；未将失败绕过。
- 现有 contract_runner.py 工具自测：1/1 通过，验证脚本能完成四动作、关联回执、暂停心跳及 STOP 退出。仅属夹具验证。
- 本机 `.local-tools/p0-integration/runner-0577987-regression-report.json` 保存真实失败证据；`runner-harness-selftest-report.json` 单独保存工具自测结果。默认 target 报告已恢复为真实失败证据，避免误读夹具 PASS。

## 2026-09-22 更新
真实 Python dea94e6 和最新 062aadd 均已通过 Java 进程级 Ready、心跳、四动作、设备集合、回执关联和 STOP 退出检查。062aadd 的状态查询协议回归 1/1 通过。此前 0577987 失败记录保留为历史证据。浏览器和 Unity 展示闭环仍待验收。
