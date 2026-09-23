# P0 剩余场景增量验证（2026-09-22）

基线：本地 ae46345，Runner 为 2fe4d1e 修复版本；本轮仅新增测试与记录，未修改生产逻辑、未重启隔离服务、未推送 GitHub。

| 用例 | 结果 | 本轮证据 |
| --- | --- | --- |
| F02 | PASS | 确认入库后保持 READY/QUEUED、零发送；替换 worker 后多次领取只发送一条对应 commandId |
| P05 | PASS | 真实 Runner 拒绝 PREPARED 状态的 PAUSE；重放一致；旧序号拒绝；下一序号 START 成功 |
| R04 | PARTIAL | 删除 owner 元数据后，读取及直接创建提案拒绝，无自动认领、无提案或执行写入；旧实例 prepare 及页面重新准备提示尚未覆盖 |

Java 定向测试 2/2 通过，失败、错误、跳过均为 0。Python 协议测试 8/8 通过（包含新增 P05 和原有 7 项）。测试执行次数不等于验收用例数。

当前覆盖：34 PASS、53 PARTIAL、9 NOT_VERIFIED、0 FAIL，共 96 项。覆盖以 [CSV 清单](P0-CASE-COVERAGE-20260922.csv) 为准；旧报告数字是历史快照。

证据：[Java 日志](evidence/additional-cases-20260922/java.log)、[JUnit XML](evidence/additional-cases-20260922/java-tests.xml)、[Python 日志](evidence/additional-cases-20260922/python.log)。Java 使用独立 H2，Python 使用真实子进程；本轮不涉及 MySQL 或真实浏览器验收。

仍需推进：I04 幂等作用域、I11 手动控制与确认竞争、P14 自然终态、F10 清理保留约束，以及 Unity 断连、旧场景和并行挑战等浏览器场景。P13 先前 STOP 非零退出的根因仍未查明，本轮未追加该项复测，继续保持 PARTIAL；不能宣布 P0 全部完成。
