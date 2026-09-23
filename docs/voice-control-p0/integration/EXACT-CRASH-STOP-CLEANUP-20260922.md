# 精确崩溃窗口、STOP 稳定性与清理入口核验

日期：2026-09-22。仅新增测试和证据，生产代码未改，未推送 GitHub；没有启用隔离服务开关。

## F03/F04：两项通过

使用实际 VoiceDispatcher，子 JVM 独立文件 H2（WRITE_DELAY=0），真实生产 Runner 与标准输入管道。SENDING 提交后进入测试 sender：

- before_write：任何命令字节写入前 Runtime.halt(73)。
- after_flush：实际 write/newLine/flush 已完成，捕获真实 Runner SUCCEEDED，但 sender 尚未返回，因此 SENT 未提交，Runtime.halt(74)。

父进程验证真实退出码，重新打开文件库确认仍为 SENDING；生产 recover/tick 重复调用后 UNCERTAIN、TIMED_OUT/UNKNOWN，commandId 不变、仅一条 execution、无通道可重发。after_flush 的真实成功未被伪造为后端已知成功。

边界：测试 sender 包装器提供崩溃点，数据库是文件 H2，不是运行中的 MySQL 后端断电；不能扩大该证据范围。

## P13：十轮通过，历史问题仍未闭环

十轮各执行真实 START/PAUSE/RESUME/STOP，等待最后回执后等待进程退出；10个退出码均为0，PID、回执、stderr尾部逐轮保存。没有复现历史exitCode=1，不能据此宣称根因已修复，P13继续PARTIAL。

## F10：真实进程清理通过，TTL范围仍缺

测试真实 AlgorithmRuntimeManager.close：真实 Runner ACCEPTED 后成功回执被透明代理扣留，关闭管理器结束进程，execution转UNKNOWN，已存回执/幂等/执行条数保留，重复close/recover不重发，管道只有一条COMMAND。

源码中的业务任务删除为 MissionServiceImpl.deleteMission 的softDelete，不删除事件和编组；此处仅完成源码审查，尚未动态验该业务入口。未发现专用P0 TTL清理入口，不编造其验收结果。因此F10继续PARTIAL。

## 证据

[精确窗口最终日志](evidence/exact-crash-20260922/java.log)、[写入前结果](evidence/exact-crash-20260922/before_write/result.json)、[flush后结果](evidence/exact-crash-20260922/after_flush/result.json)、[真实清理结果](evidence/exact-crash-20260922/fault-manager-cleanup.json)。目录另有10份stop-stability-N.json和3份JUnit XML。

首次运行参数引号错误、第二次夹具状态不一致，均未到达崩溃点；两次原始失败日志保留。第二批10轮STOP及1项清理通过但2项崩溃夹具失败；修正夹具后只重跑2项并全部通过。不要把失败批次整体写成BUILD SUCCESS。

最新覆盖49 PASS、47 PARTIAL，共96。P0仍未完成；最新修改与证据仍在本地。
