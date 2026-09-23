# 幂等作用域与取消边界增量验证

日期：2026-09-22。未修改生产逻辑，未启用隔离服务开关；本轮未提交或推送 GitHub。

## 结果

- I04 PASS：Alice 和 Bob 各自通过运行注册入口拥有独立 runtime，复用相同幂等键得到不同 proposalId；各自重放保持原提案，互相读取返回 RESOURCE_NOT_FOUND。数据库恰好两条提案和两条幂等记录，零执行、零发送。同时复测同键跨 propose/cancel 和两个资源 cancel，不串数据。
- I10 PASS：提案精确到达30秒期限后取消、运行 ended 导致提案失效后取消均返回409与对应错误码；重复尝试不改变终态，零 execution/outbox/发送。原有重复取消、取消已确认测试同时通过。

Java 定向测试 5/5，Failures 0、Errors 0、Skipped 0。本轮为独立 H2 服务层测试，没有声称真实浏览器、真实 MySQL 或真实 Runner 操作。

[测试日志](evidence/idempotency-cancel-20260922/java.log)、[JUnit 原始结果](evidence/idempotency-cancel-20260922/java-tests.xml)。

覆盖更新为47 PASS、49 PARTIAL，共96；P0仍未完成。下一步仍优先 F03/F04 精确 write/flush 崩溃窗口、P13 正常 STOP 偶发非零退出，以及 R11/F10 的真实业务域和清理入口验证。已有功能改动与证据尚未纳入 GitHub 团队基线。
