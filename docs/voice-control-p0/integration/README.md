# UAV-USV P0 联调操作清单与隔离环境配置

日期：2026-09-19。代码基线：mxy/p0-backend-20260919 / 760075d（已含 E01 prepare 扩展和 E02 画面期限）。本包准备联调环境，不代表真实 Python v1、前端或 Unity 已完成。模板本身不自动执行部署；2026-09-20 本机部署记录见 deployment-20260920.md。

## 1. 交付物与使用位置

本目录包含独立 YAML、数据库建库示例、前后端启动脚本和验收记录模板。脚本必须位于平台仓库 `docs/voice-control-p0/integration/`；下载包请放回这个位置后使用。所有命令均在平台仓库根目录执行。

| 项目 | 隔离值 |
| --- | --- |
| 后端 | 127.0.0.1:18081，仅本机监听 |
| 前端 | http://127.0.0.1:15174，/api 代理到 18081 |
| MySQL | 127.0.0.1:3306 / uav_usv_p0_integration |
| 数据库账号 | p0_integration，只授权上述独立库 |
| 网页管理员 | p0_admin，密码启动时输入；不是数据库账号 |
| Spring 配置 | 独立文件替换默认 application.yml/local，不叠加开发数据源 |
| Cookie | 会话名 P0_INTEGRATION_SESSION；仍须独立浏览器配置隔离 XSRF-TOKEN |
| 外部系统 | Gateway v1、ROS 与视觉传感器连接关闭；WSL/Editor 路径禁用 |
| P0 功能 | 默认关闭；真实 runner v1 就绪后才加 -EnableVoice |

同一主机不同端口不能隔离 Cookie；使用独立浏览器用户配置，或者只用于本次联调的隐私窗口（不要与另一个隐私窗口里的开发环境共用会话）。四人各自在自己机器运行一套；本模板不直接开放局域网访问。一个后端进程独占一个运行槽位及这套数据库，不能让两台后端共用本库。

## 2. 开始前检查

- [ ] 记录四人姓名、平台 commit、Python commit、Unity commit/构建号和前端 commit；不要仅记录“最新代码”。
- [ ] 本地修改先单独保存；确认当前分支包含 760075d，不使用 reset --hard 清空工作。
- [ ] JDK 17/21、Maven、Node >=20.19、npm.cmd、Python 及实际算法依赖可用。
- [ ] 后端包由当前代码重新构建，避免复用之前测试前的旧 jar。
- [ ] 确认 18081/15174 未被其他进程占用，不能用“杀掉全部 Java/Python”释放端口。
- [ ] 第三位同学确认真实 runner 接受 --command-protocol v1、runtime-ref、runtime-generation；Ready 使用 state，JSON 协议版本为 algorithm.command.v1。
- [ ] 前端/Unity 已支持当前 binding/challenge/report 流程；未实现则相关用例标 BLOCKED，不给缓存场景报告补新挑战编号。

## 3. 创建隔离库（手动执行一次）

由数据库管理员打开 `create-isolated-database.sql.example`，替换密码占位符后执行；凭据只保存在个人密码管理方式中，不提交仓库或发群。已有同名账号时先查权限，不自动覆盖密码或增加全局授权。

用新账号连接 127.0.0.1:3306，默认库选择 uav_usv_p0_integration，验证：

```sql
SELECT DATABASE(), CURRENT_USER();
SHOW GRANTS;
```

结果必须是隔离库与专用账号，授权仅限隔离库；不能具有开发库权限。无需把开发库复制过来，首次应用启动由 Flyway 从空库迁移；基础目录数据由项目迁移提供。初始化只创建 p0_admin，其他角色账号由测试同学通过现有账号管理能力建立；没有现成入口时使用已有自动化权限测试，不手写明文密码进用户表。

## 4. 构建与启动

### 4.1 构建

```powershell
mvn.cmd -f backend/pom.xml -DskipTests package
npm.cmd ci --prefix frontend
```

这是构建命令，不代表测试通过。不要直接执行可能加载开发数据源的全量 mvn test。首次 npm ci 需要正常依赖源网络；已有锁文件不变，不在联调时随意升级依赖。

### 4.2 只检查，不启动

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File docs/voice-control-p0/integration/start-backend.ps1 -Java 'C:/Program Files/Java/jdk-21/bin/java.exe' -Python 'D:/soteware/anaconda/python.exe'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File docs/voice-control-p0/integration/start-frontend.ps1 -Npm 'D:/soteware/nodejs/npm.cmd'
```

路径按各人机器修改。ExecutionPolicy Bypass 只作用于当前子进程，不修改系统策略；npm 使用 npm.cmd 避开 npm.ps1 限制。检查模式核对文件、程序与端口，不验证数据库凭据/连接、runner 协议、jar 是否最新或全部运行依赖。

### 4.3 启动基础环境

分别打开两个终端，在上述命令末尾加 `-Start`。后端会安全提示输入专用数据库密码和网页管理员密码，生成仅本进程使用的 integration token，退出时恢复进程环境变量；不把密码写入文件或命令行参数。后台相关外部连接保持关闭。

浏览器打开 http://127.0.0.1:15174，使用 p0_admin 登录；验证后端 http://127.0.0.1:18081/actuator/health。启动日志应只出现 p0-integration profile，不应出现 local；确认 Flyway 使用独立库。功能关闭时本人 GET 可用，新增 P0 控制写入返回 503。

Bootstrap 密码只在首次创建账号时使用，重启输入不同密码不会修改已有账号密码。遇到登录失败先核对这一点，不删除数据库来“修复”。

### 4.4 开启真实 v1 联调

仅在第三位同学的真实 runner 已就绪后，先停止隔离后端，再在后端启动命令上加 `-Start -EnableVoice`；可用 `-Runner '实际 runner.py 的绝对路径'` 指定真实实现。必须重新 prepare，旧代次不复用。准备失败即记录失败，不回退为 Mock 成功。

后端测试资源 contract_runner.py 只用于自动化管道测试，不作为真实算法联调服务。本模板不会自动换成该替身。

脚本默认检查继承的 Spring/app/server/Java 注入变量，存在时拒绝启动并只显示变量名。请使用干净终端，不盲目删全局环境变量。严格隔离依赖专用数据库权限，不能把账号换成 root 绕过问题。

## 5. 分阶段联调操作

| 阶段 | 执行人 | 操作 | 成功标准 / 证据 |
| --- | --- | --- | --- |
| L01 环境 | 后端、测试 | 核对端口、profile、DB 名称与账号 | health 正常；隔离库 Flyway 成功；无外部网关连接 |
| L02 准备 | 后端、Python | POST /api/algorithm-runs/{runId}/prepare，使用 standaloneVirtualSimulation=true 与算法负责人给出的有效配置 | 返回权威首帧及非空 ref/generation、v1 协议和实际能力；保存脱敏响应 |
| L03 幂等准备 | 后端、Python | 同一运行、同一配置再次 prepare | 身份和代次不变；不重启算法、不重置位置 |
| L04 场景 | 前端、Unity | 打开算法仿真页面，等待真实 Bridge 和场景就绪，建立绑定、申请 SCENE_READY 挑战并上报 | sceneReady=true；origin/source/绑定/代次一致；旧消息不能续期 |
| L05 START | 全体 | 获取上下文→创建 START 提案→展示冻结计划→确认→查询执行 | 201 无动作；202 只是入队；可信 Python 回执后 SUCCEEDED |
| L06 画面 | 前端、Unity、后端 | 对成功 START 申请新 FRAME_APPLIED 挑战，报告当前实际应用帧 | REPORTED_APPLIED；不超过后端权威帧且覆盖命令结果帧 |
| L07 PAUSE | 全体 | 新建并确认 PAUSE 提案 | PAUSED；无新位置帧也完成，心跳继续；NOT_REQUIRED |
| L08 RESUME | 全体 | 更新场景就绪后新建并确认 RESUME | RUNNING；不重新初始化位置；独立画面确认 |
| L09 STOP | 全体 | 新建并确认 STOP | STOPPED；最终回执先发出再退出；非整个任务成功 |
| L10 页面恢复 | 前端、测试 | 提案/确认响应丢失后刷新 | 用原请求体+幂等键恢复同一资源，不重复 apply |
| L11 展示超时 | 前端、Unity、后端 | START/RESUME 成功后停止提交 FRAME_APPLIED，继续查询 | 成功后不足 30 秒 PENDING，到 30 秒 STALE；算法仍 SUCCESS |
| L12 迟到画面 | 前端、Unity | L11 后重新申请有效挑战并报告真实帧 | 恢复 REPORTED_APPLIED；不重发算法动作，不复用过期挑战 |
| L13 未知结果 | Python、测试、后端 | 在受控 runner/harness 丢弃命令结果 | TIMED_OUT/UNKNOWN，最多只读对账，不自动重发，阻止并发新执行 |
| L14 权限与竞争 | 测试、后端 | 无登录/错CSRF/非ADMIN/跨用户、重复确认、确认取消竞争 | 拒绝零副作用；至多一个 execution/outbox/apply |
| L15 换代 | 全体 | 结束隔离旧代次并显式重新 prepare，投递旧消息 | 新 generation；旧回执不更新新运行；旧未知不被伪造成功 |
| L16 回归 | 全体 | 旧手动入口、旧帧格式、两个 Unity 页面 | 无新增重复算法驱动、权限或页面回归 |

prepare 最长依次等待 ready 60 秒与首帧 60 秒；当前前端 prepare 请求超时为 130 秒。前端请求超时先查状态，不自动重启进程。

全部 `/api/voice` POST 使用当前会话 `/api/auth/csrf` 返回的 headerName/token，并使用 UUID Idempotency-Key；同逻辑操作重试保持原键与原 body。跨用户资源统一 404。不要让同学把测试账号 Cookie 发给别人复用。

联调算法就绪状态和 Unity 就绪状态必须分别核对。算法仿真 iframe 当前资源入口是 `/unity-virtual-fleet/index.html`，由前端同源提供；实际 WebGL 构建放入对应静态目录，使用专用前端 origin http://127.0.0.1:15174，不能将消息目标设为 `*`。仓库已有页面不等于 E03 Bridge 已完成，相关回执由一/三同学交付。

## 6. 故障定位速查

| 现象 | 优先检查 |
| --- | --- |
| 后端提示数据源/账号拒绝 | 是否创建独立库、用户 host 匹配和库级授权；不要改回开发 root |
| 后端 503 VOICE_CONTROL_DISABLED | 是否在真实 runner 已准备后使用 -EnableVoice |
| runner 不识别 --command-protocol | Python v1 尚未接好，不能省略身份参数假装成功 |
| prepare 扩展字段全空 | legacy/非 standalone/未成功协商，查询对应上下文与后端日志 |
| 403 CSRF_INVALID | 独立浏览器配置、重新取得当前会话 token，检查动态 header |
| START/RESUME 的 SCENE_NOT_READY | 当前绑定的新鲜挑战、5 秒挑战期限、10 秒场景期限；不得反复上传缓存报告 |
| 执行 SUCCEEDED 但 STALE | 检查画面报告，不重新发送 START；成功后 30 秒是展示期限 |
| TIMED_OUT | 算法结果未知，保留现场并核对 commandId；不要清空 outbox 或换键重发 |
| 同学无法远程访问 | 模板只监听本机；由各自机器部署，或另外设计共享环境，不能直接改为全网监听 |

## 7. 测试与证据

先设置测试用 Python 路径，然后只运行隔离测试集：

```powershell
$env:PYTHON_COMMAND = 'D:/soteware/anaconda/python.exe'
mvn.cmd -f backend/pom.xml '-Dtest=VoiceControlTests,VoiceHttpTests,VoiceProcessTests' test
python docs/voice-control-p0/validate_contracts.py
```

JDK 需在当前终端正确配置。上述用例使用 H2/受控子进程，不是全量 Spring 上下文启动。不要直接将破坏性并发/故障测试指向本联调库；真实 MySQL 自动化另用既有随机测试库规则。

每个 L 用例在 `acceptance-record.csv` 填写 commit、环境、负责人、时间、PASS/FAIL/BLOCKED、证据及原因（未执行行保持 NOT_RUN）。保存脱敏 HTTP 响应、对应 proposal/execution/command/ref/gen、数据库记录计数和适用时 write/apply 计数。不要记录密码、Cookie、CSRF token。不得因为请求成功或表里有行就宣称 apply=1；需要 runner 侧独立计数或测试证据。

已有基线 74 项后端定向回归通过不代替本次现场记录，也不等于所有原 76 条及 X 系列跨模块验收已完成。所有要求的测试 PASS 后再宣布 P0 完成；BLOCKED 明确写缺哪个交付。

## 8. 停止与保留现场

正常结束先完成 STOP 回执核对，再在对应两个终端 Ctrl+C。保留数据库与脱敏记录，不自动 DROP 库、清空 execution/outbox 或删除审计。不确定执行保持 UNKNOWN，重启按 LOST 处理。检查这次隔离端口进程退出即可，不终止其他开发服务。

## 9. 本包验证范围

配置项已按当前项目源码核对；PowerShell 语法检查、前后端默认检查模式及 YAML 隔离配置结构检查均已通过。本次不输入凭据、不连接数据库、不启动前后端、不证明真实 Python/Unity 已通过联调。
