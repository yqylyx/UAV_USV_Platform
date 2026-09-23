# 并发、自然终态、Unity 断连验证

日期：2026-09-22。Java 基线 ae46345，本地新增测试；Runner 为 2fe4d1e 对应源码，SHA256 B3DB7E3DBA77F9E219CE302AD24F5D9E598975E97E9806DA3A947FD6608B21BD。未修改生产代码，未上传 GitHub。

## 结果

- **I11 PASS**：30 轮提案确认与手动 STOP 并发，每轮只有一个执行和发送，另一方 EXECUTION_IN_PROGRESS。另 1 项证明手动 STOP 成功后旧提案 CONTEXT_CHANGED，不能覆盖 STOPPED。Java 总计 31/31，独立 H2。
- **P14 FAIL**：1 项 Python 测试内 COMPLETED、FAILED 两个子场景均失败。确定性适配器返回 terminalStatus，生产 v1_main 发出的后续拒绝回执仍为 RUNNING。RESUME 本次确实被拒绝；不能误述为 RESUME 已错误执行。自然终态和版本未正确传播，需 Python 同学修复。
- **X19 未完成 / C04 仍部分覆盖**：首次测试匹配错误确认路径而没有卸载 iframe，保留原始记录。修正为 /api/voice/commands/*/confirm 后，真实 SCENE_READY 在 90 秒内未就绪，未进入断连步骤。这是前置阻塞，不是断连功能 FAIL。

## 复现及建议

Java：`mvn -f backend/pom.xml "-Dtest=VoiceCoverageGapTests#confirmationAndManualActionCompeteForSingleExecution+manualCompletionInvalidatesPreviouslyPreparedConfirmation" test`。

Python：`python -m unittest discover -s algorithm-service/tests -p test_runner_terminal.py -v`，当前预期会暴露失败。测试替换适配器、输入线程和 sleep，未替换生产 v1 状态处理；不等价于真实算法自然运行到终点。

P14 建议在 v1 运行循环处理有效 terminalStatus 并按契约推进 stateVersion、通过心跳公开终态；自然终态后继续拒绝动作且不重新激活适配器。修复后重跑本测试及协议、容量、Java—Runner 回归。不要把断言改成 RUNNING 来使测试通过。

Unity 下一步先定位本轮 SCENE_READY 前置超时，再重新执行真实 iframe 卸载、算法 SUCCEEDED 保持、PENDING→STALE 的验证。没有补造展示报告。

## 证据与环境

[Java 日志](evidence/concurrency-terminal-unity-20260922/java.log)、[JUnit XML](evidence/concurrency-terminal-unity-20260922/java-tests.xml)、[P14 失败日志](evidence/concurrency-terminal-unity-20260922/python-terminal.log)、[首次未注入记录](evidence/concurrency-terminal-unity-20260922/browser-initial-route-miss.json)、[第二次前置阻塞](evidence/concurrency-terminal-unity-20260922/browser-disconnect.json)。浏览器脚本在同目录，运行时需放回本机 .local-tools/browser 以使用 Playwright 和忽略的配置，设置 P0_GAP_OUTPUT；不包含密码。

服务日志在本机 .local-tools/p0-integration 的 before/after-unity-disconnect 时间戳目录备份。已关闭测试浏览器，已恢复 voiceEnabled=false、unityPresentationV1=false。服务保持运行。

覆盖清单：38 PASS、51 PARTIAL、6 NOT_VERIFIED、1 FAIL，共 96。P0 未完成，本轮新增 P14 明确失败；P13 历史 STOP 非零退出仍待定位。
