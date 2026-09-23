# P17 后端独立复测与 Java 回归（2026-09-22）

**P17 容量问题已复验通过，可以关闭。P0 整体验收仍未完成。**

## 版本与证据核对

- GitHub 分支：nly/p0-integration-20260922。
- 已抓取并核对提交：2fe4d1ed1573837c054a337bb634c5c22a0d997f。
- 受测 Runner SHA256：B3DB7E3DBA77F9E219CE302AD24F5D9E598975E97E9806DA3A947FD6608B21BD，与同学证据完全相同。
- Git blob SHA256：bcb8dbfce4f6bb113986214a7784e3154f9d743885fd93cff35553bb9b015a86。差异仅为 CRLF/LF；规范化换行后源码逐字相同。本机实际使用附件的原始 Runner 字节。
- 原指定 test-runner-capacity.py 与同学执行的脚本逐字节相同；未改容量值或通过条件。
- 仅接入 Runner 的 5 行容量修复和新增容量测试，保留当前 I05 等本地修改；未整分支覆盖、未修改数据库或启用 P0 服务开关。
- 本轮后端测试和记录尚未提交/推送；本机 HEAD 仍为 ae46345，叠加明确列出的受测修改。没有冒充整分支已经合并。

[源码与提交核对记录](evidence/p17-backend-2fe4d1e-20260922/provenance.json)

## 本机独立复测

| 项目 | 结果 | 证据范围 |
|---|---|---|
| 原指定容量脚本 | PASS，退出码 0 | 真实 Runner 子进程缓存 10000 条业务拒绝后拒绝新命令，旧回执稳定重放 |
| Python 容量＋协议 | 8/8 | 1 项容量循环测试使用 mock adapter/输入线程/时钟；7 项为真实子进程协议测试，不把两者混称全部真实算法 |
| Java 初轮回归 | 9/9，0 跳过 | 1 项真实 Ready/心跳/成员/四动作；6 项真实进程故障实例；2 项容量错误保护服务测试 |
| STOP 退出码补强 | 4 轮通过，均 exitCode=0 | 首轮日志有一次 exitCode=1 后补强；没有因此抹掉首次异常 |

容量测试确认业务拒绝计入 10000；满容量不推进序号或状态、不调用动作，旧命令查询/重放/冲突检查保留，溢出新命令查询 unknown。此处内部状态和 apply 计数来自容量循环测试，与外部真实子进程证据互补。

[本机容量结果](evidence/p17-backend-2fe4d1e-20260922/local-runner-capacity.json) · [Python 8 项输出](evidence/p17-backend-2fe4d1e-20260922/python-tests.log) · [Java 回归日志](evidence/p17-backend-2fe4d1e-20260922/java-regression.log)

## Java 遇到 CAPACITY_EXCEEDED 的行为

新增 capacityProtocolErrorProtectsChannelWithoutInventingSuccess，分别检查 relatedCommandId 为当前命令及未知命令两个分支。

- 记录协议错误审计，通道进入保护状态，后续新动作拒绝。
- 不把 PROTOCOL_ERROR 当作 COMMAND_RESULT，不生成成功回执，不改变算法运行状态/版本。
- 已发送执行先保持未决，超时后 TIMED_OUT/UNKNOWN；查询 unknown 也不会重新发送算法命令。
- 本测试是服务层注入，不声称 Java 真实进程端到端发送了 10001 条命令；真实容量拒绝由独立 Runner 脚本覆盖。

## P13：独立保留的退出稳定性观察

首轮日志记录 runId=990031、pid=13560，STOP 已获得 ACCEPTED/SUCCEEDED，但进程 exitCode=1。旧测试仅判断进程已退出，因此 Maven 仍为绿色。没有证据证明该现象由 P17 修复造成，也不能把这次退出称为正常 exitCode=0。

已补强 VoiceRealRunnerTests：直接等待 Process 退出、收集 stderr、记录 pid/exitCode，并断言 exitCode=0。补强首轮与随后 3 轮均通过，4 次退出码全为 0，首次现象暂未复现，原因仍未确定。

[首次原始日志](evidence/p17-backend-2fe4d1e-20260922/java-regression.log) · [补强结果](evidence/p17-backend-2fe4d1e-20260922/strengthened-java-four-actions.json) · [重复1](evidence/p17-backend-2fe4d1e-20260922/stop-exit-repeat-1.json) · [重复2](evidence/p17-backend-2fe4d1e-20260922/stop-exit-repeat-2.json) · [重复3](evidence/p17-backend-2fe4d1e-20260922/stop-exit-repeat-3.json)

因此 P17 更新 PASS，P13 保守回到 PARTIAL，保留退出稳定性待核；STOP 回执前 EOF 两个既有负例仍通过。不要把“首轮 9 项通过”表述成“没有任何异常”。

## 覆盖清单与后续

当前 96 条：**32 PASS、52 PARTIAL、12 NOT_VERIFIED、0 FAIL**。P17 关闭、P13 改为部分覆盖，两项状态相互独立。没有 FAIL 不等于 P0 完成，仍有 64 条未完整验收。

测试同学可将本报告、源码 commit/hash、逐方法 XML、原始日志挂接到 P17；后续继续使用加严的 STOP 退出测试，复现时保留完整 stderr 和父子进程生命周期记录，再判定清理时序或 Runner 退出原因。

可同步给团队：后端已核对 2fe4d1e 并完成原容量脚本独立复测、Python 8 项及 Java 9 项回归，P17 更新 PASS；另发现一次 STOP 后非零退出，补强后 4 轮退出码均为 0，但首次原因未明，P13 保留待核，P0 尚未全部完成。
