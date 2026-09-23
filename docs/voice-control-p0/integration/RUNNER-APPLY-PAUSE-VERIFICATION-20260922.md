# Runner 调用次数与暂停无新帧核验

日期：2026-09-22。仅新增测试，生产逻辑未改、隔离服务开关未动、未推送 GitHub。

P02/P03/P06 已补齐生产 v1_main 对适配器的直接调用计数：重放不再次应用，改变 action/parameters 冲突不改变缓存结果，落后版本 PAUSE 不调用适配器。此部分替换了适配器、输入线程及 sleep，是协议循环单元证据；结合此前真实子进程协议证据，不声称计数发生在真实运动算法内部。

P12 已使用真实 Runner 子进程验证：START→PAUSE 后连续6次 HEARTBEAT，状态PAUSED、版本2、帧号保持一致，期间零 frame；再发 STOP，最终回执后退出码0。未伪造心跳或算法帧。

先运行协议回归15/15，再单独执行新增暂停检查1/1，合计16次通过；不是一次16项完整运行，也不等于16条验收用例。

[15项协议回归](evidence/apply-count-20260922/python.log)、[真实暂停专项](evidence/apply-count-20260922/paused-real-runner.log)。

覆盖更新53 PASS、43 PARTIAL，共96。R08长时间暂停/后端持续可用性与X10 Unity在线组合仍未全部覆盖。P13历史STOP非零退出根因未定位；P0仍未完成。
