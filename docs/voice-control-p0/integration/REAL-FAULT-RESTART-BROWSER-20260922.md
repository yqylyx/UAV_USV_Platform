# 真实崩溃、后端重启与浏览器竞争证据

日期：2026-09-22。使用本机隔离 MySQL；生产 Runner 为本地 P14 修复版本。未提交或推送 GitHub。

## 已完成

1. **F08 PASS**：测试透明代理启动真实 Runner，只扣留 SUCCEEDED，不伪造任何成功事件。实际命令进入 ACCEPTED 后终止 Java，PID 从 25004 变为 17624。重启后通过真实 HTTP 查询得到 execution TIMED_OUT/UNKNOWN、runtime LOST；前后数据库快照和管道轨迹证明仅一条 COMMAND，无重发。专用 peer 账号权限在 finally 恢复。
2. **真实 Runner 崩溃及 STOP EOF 3/3 通过**：接受后强制结束真实子进程、STOP ACK 前 EOF、STOP 最终成功回执被扣留后 EOF；均不虚构成功、不重发。Java 调度器/H2 配真实生产 Runner 子进程和故障代理，并非全程 MySQL 部署测试。
3. **X08 PASS**：最终真实浏览器轮先创建提案，再扣留 SCENE_READY challenge HTTP 响应 8 秒，同时确认 START。断言在扣留区间已收到 SUCCEEDED，challenge 同时在途最多 1 条；其后真实 FRAME_APPLIED 完成 REPORTED_APPLIED。没有伪造正向 Unity 报告。

## 证据

- [真实重启请求与断言](evidence/real-fault-restart-20260922/http-restart.json)
- [PID 与 jar 指纹](evidence/real-fault-restart-20260922/restart.json)
- [重启前数据库](evidence/real-fault-restart-20260922/before-restart.json)
- [重启后数据库](evidence/real-fault-restart-20260922/after-restart.json)
- [真实管道轨迹](evidence/real-fault-restart-20260922/runner-trace.jsonl)
- [Java 崩溃测试](evidence/real-fault-restart-20260922/java-crash.log)
- [最终浏览器竞争证据](evidence/real-fault-restart-20260922/browser-overlap-verified/browser-competition.json)

浏览器前两轮仅验证延迟和串行、没有证明时间重叠，虽然旧脚本输出 PASS，不能用它们关闭 X08；只有 browser-overlap-verified 的加强断言轮作为验收证据。生成器发生编码错误的中间尝试未改变产品代码。

## 边界与环境恢复

F03/F04 要求 SENDING 提交→write 前、flush→SENT 提交前的精确崩溃屏障，本轮未覆盖，继续 PARTIAL。P13 历史偶发正常 STOP 非零退出根因仍未确认。不得将本轮3项崩溃测试等同于整个故障矩阵完成。

测试代理已退出服务配置，已恢复正常 runner.py；功能开关 voiceEnabled=false、unityPresentationV1=false，测试浏览器关闭。服务日志备份在本机 .local-tools/p0-integration/after-real-fault-*，重启前日志另外保存在本证据目录。

覆盖：45 PASS、51 PARTIAL，共96项。P0仍未完成。
