# P0 边界增量验证

日期：2026-09-22。基线 ae46345 加本地测试；生产 Runner 为 2fe4d1e 修复版本。本轮未修改生产代码、未重启服务、未推送 GitHub。

| 用例 | 状态 | 实际检查 |
| --- | --- | --- |
| I01 | PASS | 201、30 秒有效期、1 提案、无执行/待发送记录或管道写入 |
| I02 | PASS | 延迟重放返回 200，提案与到期时间不变 |
| I04 | PARTIAL | 同键跨 operation 和资源不串数据，其他用户不能取消；两名用户各自资源同键成功仍待测 |
| P04 | PASS | 真实 Runner 拒绝旧序号及跳号，下一合法序号仍成功 |
| P06 | PARTIAL | 落后版本被拒绝且状态版本不变，后续合法 PAUSE 成功；尚缺适配器调用直接计数 |

最终 Java 定向测试 2/2、Python 真实子进程协议测试 10/10 全部通过。初次 Java 1 项失败是新增测试误将提案待确认状态写为 PENDING；对照契约修正为 AWAITING_CONFIRMATION 后通过，生产代码未改。

[Java 最终日志](evidence/additional-boundaries-20260922/java.log)、[初次测试断言错误](evidence/additional-boundaries-20260922/java-initial-test-assertion-error.log)、[JUnit XML](evidence/additional-boundaries-20260922/java-tests.xml)、[Python 日志](evidence/additional-boundaries-20260922/python.log)。Java 使用独立 H2，未操作业务数据库；Python 启动真实 Runner 进程，不代表 Unity 浏览器验收。

最新 96 条覆盖：37 PASS、51 PARTIAL、8 NOT_VERIFIED、0 FAIL。以 [覆盖清单](P0-CASE-COVERAGE-20260922.csv) 为准，先前报告为历史快照。

未完成重点：I11 确认与手动控制竞争、P14 自然终态、F10 清理约束、Unity 并行挑战/断连/旧场景恢复；P13 历史 STOP 非零退出原因仍未定位。本轮未补跑这些场景，不能宣布整个 P0 完成。
