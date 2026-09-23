# 查询关联与计划哈希增量验收

日期：2026-09-22。本轮仅修改测试与文档，没有改生产逻辑或启动隔离服务，未推送 GitHub。

P20 PASS：生产 Dispatcher 收到 STATUS_REPLY 时，内层 commandId/runtimeRef/runtimeGeneration 与外层不一致，或外层 queryId/commandId 不匹配，共5种负例均触发通道保护；执行保持 TIMED_OUT/UNKNOWN，运行状态和版本不变，零命令回执入库，仍只发送1条命令。另设合法关联正例，恢复为 SUCCEEDED/SUCCESS。未知结果只读、查询次数上限的已有测试同时通过。

I12 PASS：从初始 USV/UAV 输入顺序换为 UAV/USV 后创建新提案，两个 proposalId 不同，但完整 plan 与 planHash 相同，explicitDeviceCodes 排序稳定。Java/Python 黄金哈希与契约校验同时通过。

先执行8项查询专项，补哈希断言后最终10/10通过（0失败、错误、跳过）；不能相加声称18项独立用例。契约脚本通过48正负样例、6prepare、golden hash和文档链接检查；76业务用例只是设计清点，未由该脚本执行。

测试范围为独立H2、生产Java服务与协议夹具；本轮无真实Python/Unity故障注入。P20结合之前真实STATUS_QUERY正常恢复证据，不混称本轮五个负例均来自真实Python进程。

[最终Java日志](evidence/query-correlation-20260922/java-final.log)、[契约检查](evidence/query-correlation-20260922/contracts.log)，同目录保存JUnit XML与哈希清单。

最新覆盖55 PASS、41 PARTIAL，共96，P0尚未完成。仍需补权限代理组合、真实iframe重载、功能开关在途对账、真实业务删除及历史STOP退出问题等。
