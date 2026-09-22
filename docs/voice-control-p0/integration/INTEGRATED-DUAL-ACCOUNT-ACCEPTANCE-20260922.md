# 最新代码整合与本机双账号真实验收

日期：2026-09-22。独立分支：`mxy/p0-local-acceptance-20260922`。

## 结论

已整合远端最新 `3e37759`（包含后端和测试分支历史）与本机停止探测、终态恢复、单次重同步意图保留修复。本地代码提交 `77d8955972d621acc74c374919d3df2c720caffe`，未推送 GitHub。

本机真实 Edge / Python / Unity WebGL 联调通过；真实同标签页双账号 A→B→A 检查通过。前端 20/20 回归测试通过，类型检查与生产构建通过。构建仅有体积提示。

这不等于 96 条全部通过。受控晚消息、运行中撤权、后端进程重启、STOP 回执前 EOF 等反例仍须独立验收。

## 环境和证据边界

- 本机隔离数据库 `uav_usv_p0_integration`；后端 18081、前端 15174。
- 两账号：`p0_admin` / `p0_peer_20260922`，均为 ADMIN；第二账号使用独立随机密码，仅存本机忽略目录。
- 后端及 Runner 源码本轮未修改，沿用已验证 jar；实际文件哈希写入 manifest。
- WebGL 使用远端集成提交携带的资源，团队标注 Unity 源提交 ab1f8a0；本轮未重新构建 Unity。
- 每个浏览器步骤自动保存对应数据库只读事务快照。浏览器仅记录 voice/algorithm-runs 请求，不记录登录请求、Cookie、Authorization、CSRF token 或密码；保留 Idempotency-Key 供核对。
- 四动作恢复与双账号使用不同运行，分别留证；没有拼接为同一条执行链。

## 主链路关联身份

runtimeRef：`844acca0-3c84-48ad-9e90-7ec7af717bca`  
runtimeGeneration：`fafa9a27-9bf9-42d4-b5b9-5cc0afcf1eb4`  
algorithmRunId：`1790075460800`

| 动作 | proposalId | executionId | commandId | 最终展示状态 |
|---|---|---|---|---|
| PAUSE | 691d792b-7e65-42da-b1b4-9a3de6232743 | 6b9f3f0c-cb9f-4ee6-a1ea-091dd529bfd4 | 1fa70010-87d0-4509-bc46-ad1f20a603fc | NOT_REQUIRED |
| START | 04749d5c-ba39-4f0c-a61c-0e2585c87d9b | 786d50e2-ab59-405a-b5b0-bb954b153abc | 28e95e65-0517-42da-aba4-bcaa1e0c832b | REPORTED_APPLIED |
| RESUME | 3d738830-2101-4c44-b954-9466ee360d63 | 8114f883-a636-446a-a30f-412e16ae5fde | 50591297-0871-40a9-ad10-9f9281aaf26a | REPORTED_APPLIED |
| STOP | b73eb340-3939-4cf2-a0db-1ce7c38e4ad0 | a9a73721-0a70-4f27-9f13-82d24c5c4999 | c6c2a984-56dd-4361-a51b-4c9327f54cab | NOT_REQUIRED |

四条 execution 均 SUCCEEDED，每个动作各一条；START/RESUME 均真实 REPORTED_APPLIED。该运行的 prepare POST 仅一次，运行中刷新及 STOP 后刷新均保持原运行。

### 确认响应丢失并过期后的恢复

PAUSE 响应实际已由后端处理，浏览器受控丢弃响应。提案过期：`2026-09-22T11:11:55.447909Z`；恢复时读取既有 execution：`2026-09-22T11:12:15.817Z`，均 UTC。

实际恢复方式为查询已确认提案及 execution，没有第二次 confirm POST，更没有第二条 PAUSE 命令。原确认 Idempotency-Key 与数据库幂等记录关联一致。不得描述成“已验证第二次 POST 重放”，因为本轮没有走该分支。

### 展示超时与新挑战

- 首次观察 PENDING：`2026-09-22T11:12:19.319Z`。
- 首次观察 STALE：`2026-09-22T11:12:49.441Z`，约 30 秒；数据库 deadline 见 db-resume-pending.json。
- 首次观察 REPORTED_APPLIED：`2026-09-22T11:13:13.765Z`。
- 恢复 bindingId：`04667029-e2e4-4e14-a351-9b6eb2da1a67`。
- 新 requestId：`36e6dba3-403d-4a04-85c9-18ba03abe7a1`；sequence：2；真实 frameSequence：616。

恢复前后 RESUME 的 executionId/commandId 不变。截图、受控断报 markers、challenge/report 以及数据库快照均保留。轮询首次观察时间不是内部状态变更的精确时刻。

### STOP 退出

原始 Java 日志记录主运行正常退出；具体 PID/exitCode 见 runner-correlated.log。主运行和双账号三次运行均能逐一匹配 exitCode=0。没有以数据库成功状态替代进程退出证据。

## 真实双账号结果

| 所有者 ID | runtimeRef | algorithmRunId |
|---|---|---|
| 1 | 5c3e2b38-a37e-4bae-8173-0356dde60ca0 | 1790075904910 |
| 2 | 684d4cb7-e3e0-4bf9-a14a-01f56d998f2b | 1790075931593 |
| 1 | 9232cb93-0691-4ae8-91ae-ed78e44c673d | 1790075962418 |

- A 登录、创建并停止自己的运行，然后真实点击退出；A 的控制日志、展示日志和场景快照被清除。
- B 在同一标签页登录，经页面链接进入仿真。页面不显示 A 的运行，contexts 列表不含 A 的资源；访问 A 的 context、proposal、execution 均 404 RESOURCE_NOT_FOUND。
- B 创建并停止自己的运行后退出，B 的恢复缓存被清除。
- A 重新登录，页面及 contexts 不含 B 的运行；访问 B 三类资源均 404；读取 A 自己的历史 execution 返回 200。
- 最后退出，未登录 contexts 返回 401 UNAUTHORIZED。

共保存 13 条账户检查结果。6 个 404 和 1 个 401 是预期拒绝，不是系统故障；主链路记录中没有 HTTP 4xx/5xx。两组 pageerror 均为空。

本轮没有注入旧账号迟到消息、撤销正在运行账号的权限或测试多标签页；X17 保留 PARTIAL，不能仅凭双账号正常切换覆盖这些变体。

## 失败和脚本修正留档

1. 第一轮刷新后过早 RESUME，被 SCENE_NOT_READY 正确拒绝；脚本改为等待真实 SCENE_READY 报告成功，保留门禁证据。
2. 主链路已完成后，组合脚本登录 B 默认进入系统总览，却直接寻找隐藏的语音面板，导致脚本导航超时；core/failure.txt 和 failed 步骤保留，不代表主链路失败。双账号改为通过实际“算法仿真”链接切换，并用独立脚本完成。
3. 上述中断留下 B 的准备运行，A 新建运行收到 RUNTIME_BUSY；已由 B 自身身份正常停止，随后重新验收。未通过清库或跨账号强制覆盖规避保护。

原始未通过轮次保留于本机 .local-tools/browser/acceptance-dual-3e37759 和 acceptance-accounts-3e37759；摘要附在 exploratory-checks.json。

## 文件导航与收尾

- `evidence/integrated-3e37759-20260922/core/`：四动作、过期恢复、展示闭环、刷新记录和每步数据库快照。
- `accounts/dual-account-checks.json`：账号切换及访问检查；accounts/db-dual-account-complete.json：所有者与执行记录。
- `readonly-export.sql`：各组只读 SQL；backend.out.log / runner-correlated.log：真实进程日志。
- `P0-CASE-COVERAGE-20260922.csv`：按原 96 条 ID 更新精确覆盖范围；未测项不提升为 PASS。

临时账号已停用，记录保留；所有验收运行已停止，浏览器已关闭；隔离前后端继续运行，P0 与 Unity v1 临时开关恢复关闭。证据经过实际凭据值扫描，源码与证据另附 SHA-256。
