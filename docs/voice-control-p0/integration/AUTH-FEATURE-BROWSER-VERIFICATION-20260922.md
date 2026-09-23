# P0 权限、故障与真实浏览器补验

基线 ae46345f + 本地未提交修复。最终 96/96 PASS，0 PARTIAL；尚未完成最终验收。

## 已通过

- A04：所有运行/提案/执行/绑定/挑战/报告的跨用户读写拒绝，资源不变。
- A05：真实 Spring 代理校验数据库撤权和禁用，缓存 ADMIN 无法绕过。
- A07：六个写入口逐一验证超16KiB返回413、错误媒体类型415，零业务写入。
- A08、X18：关闭功能拒绝新写，在途回执仍落库且GET可读；真实Runner旧手动四动作可用。
- P07：修复适配器 ValueError 杀进程问题；18项Python测试及Java真实四动作通过。
- X14：真实提案响应丢失后刷新，同path/body/key恢复相同提案。
- R03：真实存活进程槽位占用拒绝，原进程保持存活。
- X10：真实暂停16秒无新位姿，心跳推进且多次真实场景回执成功。
- P19：真实适配器线程阻塞，进程存活但心跳停止；后端拒绝新动作、不伪造成功。
- F05：回执表故障期间另一运行排队命令不发送，恢复补账后才发送。
- C03：真实202 QUEUED未提前显示SUCCESS，解除查询阻断后实际完成。

## 新增证据但仍未判定完整通过

- X04：READY58秒及首帧58秒分别等待成功，READY超过60秒拒绝；首帧超时首次因中英文文案断言失败，正在单独复测。浏览器超时不重复启动待补。
- X05：真实丢失前三条HELLO后握手恢复；重复HELLO不重建场景的明确计数待补。
- X07/C05：真实iframe重载产生新实例/绑定，旧消息零HTTP报告；新实例revision重新起算，不能称作跨实例递增。
- R08：16秒暂停保持健康已补；此脚本尚未点击RESUME。
- I08：二次confirm POST返回同执行已补；首次确认响应实际丢失再POST的组合仍待补。

## 限制与运行方式

原始证据在 evidence/auth-feature-20260922，保留首次失败日志。Java故障测试使用H2；真实浏览器使用本机隔离MySQL、真实Python和Unity WebGL，没有伪造成功展示报告。

P07仅捕获明确的ValueError业务异常，返回FAILED/ADAPTER_ERROR，协议状态和版本不推进；不声称回滚适配器内部副作用，不吞掉未知程序错误。修复后后续合法命令可继续。

归档浏览器脚本从原.local-tools/browser目录运行，依赖已安装Playwright及忽略的本地隔离凭据；未归档凭据。P0功能临时开启用于验收，结束须关闭并保存日志。

Runner SHA256: `7e869c1fd56d81b2f41c06479f9df33bab4493a50d8f77c98932f31b9b9e6308`

## 后续组合复测更新

- **X01**：legacy-prepare.log + 既有正常及重复prepare验证：扩展/legacy/能力子集/失败均通过，等待期限另按X04。
- **X02**：ready-field.log：runtimeState别名不能完成READY；state正例通过。
- **X03**：python-query-cli.log：真实短参数v1协商长协议名，长协议名CLI拒绝；13项通过。
- **R08**：paused-resume-browser/browser-paused.json：暂停16秒后真实恢复RUNNING且Unity已应用。
- **I08**：confirm-lost-browser/browser-proposal-recovery.json：实际202响应丢弃后重试同一确认，200返回原执行。
- **X09**：report-replay-retest-browser/browser-report-replay.json：新报告阻断12秒，同key200/新key409，sceneReady仍false。
- **P16**：stdout-boundary.log：真实管道连续三条超256KiB/错身份/普通日志，均保护通道，零执行。
- **I07**：real-concurrent-apply.log：12线程不同key确认，仅1execution/outbox/COMMAND/真实adapter START。
- **I09**：real-concurrent-apply.log：confirm/cancel竞争，真实adapter START数量等于获胜execution且至多1；结合既有100轮双方结果。
- **C07**：legacy-regression.log：62项旧任务/设备/登录数据/控制安全回归，结合已归档真实登录及HTTP四动作。
- **C08**：secret-scan.json：781个可交付文本扫描实际本机秘密值、会话Cookie和私钥特征，无命中；不包含忽略的本地配置或二进制归档。

首帧60秒期限复测通过，原失败仅为测试断言要求中文文案；报告重放初次404为取证脚本路径错误，已改用捕获的实际URL并通过。原始失败日志保留，不算产品缺陷。

## 最终缺口补验（整组615项后端回归通过）

- **X04**：prepare-deadline-*.json / prepare-frame-deadline-retest.log / prepare-timeout-browser：三个真实等待窗口、提前退出及浏览器133秒仅一次prepare。
- **X05**：hello-repeat-browser：丢前三次HELLO后恢复，再重复10次不换绑定/场景或重复prepare。
- **X07**：iframe-browser + scene-revision-browser：换iframe新实例与同实例sceneRevision递增分别验证，旧报告零HTTP。
- **X13**：既有coverage-gaps/http-gaps.json及db-before/after-restart证明持久期限与成功结果保留；既有真实STALE重新同步闭环与本轮服务层迟到报告测试。重启后LOST的旧运行不得视为合格展示来源。
- **X16**：stale-proposal-browser：响应丢失、真实状态变化、刷新仍原body/key，旧确认409 CONTEXT_CHANGED。
- **X17**：role-revoked-browser：真实运行撤权后刷新，缓存提案确认403、零新增执行；结合既有A→B→A隔离及旧消息拒绝回归。
- **R02**：proposal-generation.log：真实进程替换使旧提案INVALIDATED，确认409 PROPOSAL_INVALIDATED；仍待确认的代次不匹配409 GENERATION_MISMATCH，均零新进程写入。
- **R04**：ownerless-process.log + frontend-ownerless.log：真实进程缺归属不能被prepare认领/不能创建执行，UI提供重新生成及管理员清理指引。
- **R06**：plan-policy-before.log / plan-policy-after.log：四维冻结计划检查；补策略版本确认和发送前校验，37项通过。
- **R11**：business-run-isolation.log：实际Runner业务任务路径不登记独立P0运行、不选择其他实例，结合既有ROS/域注入拒绝。
- **P09**：old-result-correlation.log：runtimeRef/代次/来源进程/未知command四边界不改执行或运行状态。
- **P11**：old-result-correlation.log：真实旧成功回执只补旧execution，旧ACCEPTED不回退，新运行快照不变。
- **P13**：stop-cleanup-before/after.json + stop-cleanup-after.log：可控退出窗口重现清理杀进程1，修复后0；六项含四动作、EOF两窗口、死锁、未知清理通过。
- **P18**：python-query-cli.log + old-result-correlation.log：真实已知/未知查询与退出后不查询，不重发；旧执行只合法补账。
- **F10**：business-cleanup.log + 既有manager-cleanup/7天老化：真实业务服务软删除保留未知执行及幂等/出站记录。未实现专用TTL清理，不宣称执行过不存在的定时任务。
- **C05**：iframe-browser + page-return-browser：真实重载及切换总览返回，新会话拒绝旧报告；结合既有刷新恢复。
- **C06**：dual-protocol-pose-check.json + frontend-final.log：真实legacy位姿回执与P0报告帧关联、Transform匹配且零未知设备；坐标转换和重放回归通过。

### 验收预期澄清（不是放宽安全要求）

R02原清单只写GENERATION_MISMATCH，但接口契约同时明确确认已失效提案返回PROPOSAL_INVALIDATED。真实进程退出会先失效提案，因此按先后状态拆分两条断言；两者都要求409、旧提案失效、新进程零命令。X13区分持久化期限恢复与仍存活运行的合法迟到展示；后端重启后旧运行LOST，不允许为追求通过而伪造就绪。

### 本轮实际缺陷

- P07：适配器业务ValueError导致进程退出，已返回FAILED/ADAPTER_ERROR并保留后续命令能力。
- P13：清理立即destroy可打断STOP成功后的正常退出，已先关闭stdin并等待2秒，再逐级终止。修复前可控退出窗口exit1，修复后exit0；历史13560进程日志显示清理先于exit1约18ms，与该竞态一致，但不声称重演历史现场。
- R06：旧policyVersion原可确认及发送，现两阶段拒绝并失效。保留修复前2项失败和修复后37项通过日志。

615项后端、32项前端测试通过，前端生产构建通过。首次JAR打包因运行服务占用文件失败；保存日志停对应后端后重新打包成功。C01部署后关闭开关的真实HTTP检查尚待完成。

## 收尾结论

C01关闭模式真实HTTP四动作通过，0语音execution；MySQL32/32、Python20/20、前端32/32与构建、后端615次执行全部通过。最新JAR真实浏览器闭环通过，数据库4条execution，STOP exit0。最终服务开关均已关闭。前述“待补/正在复测”为本轮中间记录，以 [最终报告](P0-FINAL-ACCEPTANCE-20260922.md) 与CSV为准。
