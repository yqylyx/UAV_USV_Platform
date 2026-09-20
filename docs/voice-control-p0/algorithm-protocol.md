# P0 Java ↔ Python 命令协议

版本 algorithm.command.v1；传输为专属子进程 stdin/stdout 的 UTF-8 NDJSON。本文是待实现契约。

## 1. 启动、身份与协商

后端启动新进程时，通过拟新增启动参数传入 runtimeRef、runtimeGeneration 和 command-protocol=v1；参数只能由服务端产生。runner 的 runtimeReady 声明 runtimeRef/generation、protocolVersion、adapterId、capabilities、state/stateVersion。

旧 runtimeReady 没有协议字段：继续原手动流程，P0 新写请求拒绝。不得在同一新进程中混用无 commandId 的旧命令；原手动 Controller 在 v1 模式经适配器补齐同样的命令信封，保持用户操作兼容。

每条输出绑定读取它的 RuntimeHandle：字段中的 runtimeRef/generation 必须和该句柄匹配，不能仅凭输出字段把消息路由给其他实例。后端重启后新 generation 不接管旧执行。

capabilities 首版为 START/PAUSE/RESUME/STOP 的实际支持子集；协议可以声明未来动作，但 P0 上层白名单只允许这四种。不要仅因算法名为 ESCORT_GUARD 就声明 ACTIVE_CAPTURE。

## 2. 命令结构

Command Schema 定义：protocolVersion、kind=COMMAND、commandId、runtimeRef、runtimeGeneration、commandSequence、expectedStateVersion、action、parameters={}。

commandSequence 为当前代次专用的正整数命令序号，与算法帧序号及 eventSequence 完全独立。后端串行分配；新合法命令应为 lastCommandSequence+1。先查 commandId 去重，再检查序号：同 ID 同内容重放缓存回执，不重复应用；同 ID 不同内容拒绝 COMMAND_ID_CONFLICT；未知 ID 的旧/跳跃序号拒绝 SEQUENCE_MISMATCH，不推进序号。

有效结构且序号正确的命令即使因 INVALID_STATE 被拒绝，也消费该序号并缓存结果，避免之后命令无法继续。字段错误、身份错误、冲突和序号错误不改变执行状态或序号。

expectedStateVersion 与运行实时状态比较，不相同返回 STATE_VERSION_MISMATCH。状态转换成功递增 stateVersion；普通帧、心跳、去重回放和拒绝命令不递增。相同业务状态的重复新动作依状态表拒绝，不能伪造一个新版本。

## 3. 回执及命令查询

Result Schema：kind=COMMAND_RESULT、protocolVersion、commandId、runtimeRef/generation、eventSequence、status、runtimeState、stateVersion、lastFrameSequence、errorCode、affectedDeviceCodes。

status：ACCEPTED、EXECUTING、SUCCEEDED、REJECTED、FAILED。正常动作最少返回 ACCEPTED→SUCCEEDED；直接拒绝仅返回 REJECTED。每命令 eventSequence 从 1 开始连续递增；重复返回已缓存结果时保持原序号和内容，不重新生成事件。SUCCEEDED/REJECTED/FAILED 后不得退回中间状态。

affectedDeviceCodes 列出本次动作实际涉及的设备 canonical code，必须属于冻结集合；P0 暂停/停止等全局动作成功应与冻结集合一致。集合不匹配、未知 commandId 或错误来源的事件记为协议异常，不能据此成功结算。

后端持久化每个有效事件，按最高已应用序号推进；如果先收到终态后收到相同命令的旧 ACCEPTED，保留终态，重复不新增审计事件。同序号不同内容隔离为协议错误；不能把“任意后到事件”当作最新状态。由于管道有序，实际乱序通常来自队列重投递；测试仍需覆盖。

StatusQuery Schema：kind=STATUS_QUERY、protocolVersion、queryId、commandId、runtimeRef/generation；不消费命令序号。StatusReply 返回 kind=STATUS_REPLY、queryId、身份、known、result。known=true 时 result 为已缓存的最新 CommandResult；false 时 result=null。查询不执行动作。已退出进程无法查询时，后端仅能使用已持久化回执；UNKNOWN 不等于可安全重发。

结果缓存保留到该代次结束；上限 10000 个命令，达到上限后不淘汰已执行命令，拒绝新命令 CAPACITY_EXCEEDED，并要求结束后重新准备。这个容量拒绝不推进命令序号。跨进程不承诺缓存存活；代次丢失按 UNKNOWN 处理。

### 3.1 协议错误独立通道

MALFORMED_MESSAGE、IDENTITY_MISMATCH、COMMAND_ID_CONFLICT、SEQUENCE_MISMATCH、CAPACITY_EXCEEDED 使用 `kind=PROTOCOL_ERROR`，见 ProtocolError Schema。relatedCommandId 可为 null；身份字段由实际 runner 启动上下文填充，不回显伪造的入站身份。

这些协议错误不发送一个冒用旧 commandId 的 COMMAND_RESULT(REJECTED)，不覆盖原命令缓存或后端执行状态；后端只记录诊断并标记通道异常/进入只读对账。合法新命令通过协议层后，状态或业务不满足才用 COMMAND_RESULT(REJECTED)。这样同ID不同内容不会将已成功的原命令误改为失败。

## 4. 状态变化与退出

运行状态允许 PREPARED/PREVIEW/RUNNING/PAUSED/STOPPED/CANCELLED/COMPLETED/FAILED。LOST 仅由后端描述不可达，不由 runner 自称。

START、PAUSE、RESUME、STOP 按 interface-contract.md 状态表执行。操作在算法线程/命令队列中串行应用；不得与 step 并发修改状态。

PAUSE 的 SUCCEEDED 表示已在步进边界停止继续推进，附最后有效帧序号；不要求生成一帧新的位置。RESUME 不重新 prepare、不重置位置。STOP 的 SUCCEEDED 表示算法不再步进，先 flush 最终回执，再清理资源退出。后端可独立记录清理超时，不把已生效 STOP 反向改写为未生效。

算法自然完成或失败后保留只读状态查询和心跳最多 30 秒，然后清理退出；期间拒绝 START/RESUME，STOP 不用于把已完成任务改为另一终态。异常导致无法可靠确认是否应用的命令不能返回成功；尽可能发 FAILED，进程断开由后端对账。

预期的用户/业务错误（非法动作、非法状态、能力不支持）捕获为 REJECTED，进程继续工作；不可恢复算法异常转 FAILED 并结束运行。未知 action 不能只发 stateChanged。

## 5. 心跳、帧与显示证据

Heartbeat Schema：kind=HEARTBEAT、身份、protocolVersion、heartbeatSequence、runtimeState、stateVersion、lastFrameSequence。每 1 秒发送，PAUSED/PREPARED 也持续发送；应与健康的算法工作循环关联，不能由完全独立线程在算法已死锁时仍报告可执行。

后端以本机收到合法心跳的单调时钟判断 5 秒过期，不信任跨进程墙钟；START/RESUME 的场景报告默认 10 秒有效。两项均为可配置设计默认值。

v1 runtimeReady 与现有 frame/stateChanged 可共存，Java 在所属 RuntimeHandle 上为帧绑定 generation；现有算法 frame payload 不必为 P0 全量改写。stateChanged 不可取代 COMMAND_RESULT。收到帧也不能证明某一命令已成功。

场景/画面报告仅通过现有授权页面关联到 runtimeRef/generation，不新增匿名“执行成功”HTTP 入口。P0 不要求 Unity 把算法命令再执行一次。

## 6. 超时与崩溃默认值

- outbox QUEUED 超过 10 秒未领取：未写出时 INVALIDATED，原因 DISPATCH_DEADLINE_EXCEEDED。
- flush 后 5 秒未收到 ACCEPTED 或终态：TIMED_OUT，outcome UNKNOWN，不盲重发。
- flush 后 15 秒未收到最终结果：TIMED_OUT；P0 四个动作应在短时间生效，未来长动作另定义期限。
- TIMED_OUT 原代次仍可靠存活时最多发起 3 次只读 STATUS_QUERY，间隔 2 秒；不重发 COMMAND。次数用注入时钟测试，不真实睡眠。
- 数据库在发送后不可用：不再发送新命令，保留运行通道并尝试落地事件；恢复后通过同代次查询补账，不能伪造持久化成功。
- 管道最多 256 KiB/行；超大行按有界缓冲排空并记录协议错误，连续 3 次结构/身份违规将通道标不可用。stdout 日志不以“包含 JSON”自动成为控制消息；普通日志走 stderr。

## 7. P0 不变量

1. 未经确认或未持久化的命令不得写入 stdin。
2. 同 commandId 对同 generation 最多一次业务应用；进程重启不自动复用命令。
3. 旧代次事件不得修改新运行状态。
4. stdout 来源、字段和协议均验证后才更新状态。
5. HTTP 200/202、模型解析结果、stateChanged 或 Unity 显示回执都不能单独把 execution 改为 SUCCEEDED。
6. 所有 fixture 是虚构 ID 和状态，不含真实设备控制目标。