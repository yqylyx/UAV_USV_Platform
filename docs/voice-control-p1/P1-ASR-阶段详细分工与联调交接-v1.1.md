# UAV-USV P1-ASR 阶段详细分工与联调交接 v1.1

配套规划v1.3。

日期：2026-09-23；状态：D1最终确认稿。独立文件识别已通过；浏览器系统接入未验收；准确率尚未评估。文档确认不代表接口已经实现。

## 1. 人员与统一部署

| 成员 | 职责 |
|---|---|
| nly | 前端录音与文字展示、Python ASR服务、Unity兼容检查 |
| mxy | Java接口与ASR适配、部署配置、D01–D12测试与证据汇总 |
| 双方 | 共同确认接口；nly复核关键演示结果，避免仅由实现者自测结案 |

首轮统一部署在mxy的i5-10500／UHD630／约16GB电脑，Java、Python ASR、演示浏览器同机。ASR仅监听127.0.0.1:18082；演示浏览器用localhost（例如http://localhost:15174）。部署需核对代理、Cookie和CSRF，不混用localhost与127.0.0.1的浏览器会话。

候选模型配置small＋CPU INT8＋4线程，最终以该机实际联调结果确认；启动加载并预热，请求期间不下载模型。依赖、模型revision/SHA256及线程配置写入部署清单。nly的i7-12700／UHD770／32GB只用于开发和辅助测试，不用其耗时代替部署机验收。

历史A机文件测试：录音6为5.784秒，base为1.21/1.13秒，small为3.27/3.55秒，CPU INT8/4线程。nly反馈的B机small/8线程离线1.84/1.76秒，来源F:/Tool/asr-cpu-test/result-small-offline.json；当前编辑环境未读取该F盘JSON，须提供脱敏原件归档。两组记录不能混作同一次测试，且均不等于浏览器端到端耗时。

## 2. 功能与阶段

D1只做录音→本地识别→显示、编辑文字，不接意图大模型、不生成提案、不执行控制指令、不依赖算法实例与Unity就绪。前端经Java调用独立Python ASR，不直接访问Python。Python独立环境/进程，不改算法Runner；Unity无新增功能，只做兼容。原P0手工控制独立保留。

首轮完成标准：不启动仿真，页面录一段中文，真实本地模型返回文字且可编辑；说“停止任务”也只显示文字，不执行任何动作。

D1只验收D01–D12。E1持久化、跨重启保障、五格式和统计评测以及原46项完整用例继续待办，不能因D1通过标记E1完成。规划统一引用v1.3、分工统一引用v1.1，旧v1.2仅历史来源。没有新增查询、取消或复杂任务管理接口。

## 3. 公共接口与音频

POST /api/voice/intelligence/transcriptions，multipart由浏览器自动生成boundary。字段requestId小写UUID、locale=zh-CN、唯一audio；X-Request-ID、Idempotency-Key均等于requestId；动态CSRF头保留。仅当前启用ADMIN，返回前及重放复核权限。登录/权限/CSRF/基础字段、大小限制不可省略；ASR不要求runtimeRef。

D1明确支持部署清单指定版本Chrome/Edge的WebM/Opus与MP3文件测试；浏览器版本在部署时记录并冻结。其他格式留E1，不在页面宣称支持。服务端验证真实容器、codec、可解码性，不只信任MIME。拒绝视频轨道、超过2声道或48kHz输入；受限转换16kHz单声道，最多960000采样点。

大小为**1字节至5MiB（5242880字节）**；完整multipart≤6MiB。页面约58秒软停止，等待最终编码Blob；实际文件上限60000ms。计时与编码尾帧可能有延迟，软停止不能保证所有文件合规；实际时长由后端解码测量并向上取整毫秒。超限413 VOICE_AUDIO_TOO_LONG并提示重录，不裁剪、不伪造时长。界面明确“最长录制约58秒，文件上限60秒”。

文本最多500个Unicode码点，完整展示，不套用意图解析200字限制。无语音422 VOICE_NO_SPEECH，超长422 VOICE_TRANSCRIPT_TOO_LONG。成功HTTP200，外层{code:SUCCESS,message,data,timestamp}，data为requestId、text、locale、durationMs、provider=local-asr、model=冻结公开别名；错误data=null。no-store，合法ID回显X-Request-ID；无秘密、堆栈或内部路径。

## 4. D1幂等最终规则

优先复用已有可用持久化幂等实现；尚未实现时采用以下内存方案，选择结果写入部署清单，不能假设已有实现。

| 项目 | 约定 |
|---|---|
| 范围 | userId + endpoint + requestId |
| 内容指纹 | 原始音频SHA256＋locale＋规范化基础MIME，以无歧义结构编码；不含boundary/文件名 |
| 最大记录数 | 全局1000条，含处理中及缓存终态，原子占位 |
| 终态保留 | 完成后30分钟，之后清除文字和记录；重放不续期 |
| 清理频率 | 每分钟清理过期终态，处理中不得清理 |
| 容量满 | 新键429 VOICE_RATE_LIMITED及Retry-After；已有键仍可查询式重放 |
| 同键同内容处理中 | 409 VOICE_REQUEST_IN_PROGRESS，Retry-After:2 |
| 同键同内容完成 | 返回原结果及原timestamp，不重新识别 |
| 同键不同内容 | 409 IDEMPOTENCY_CONFLICT |
| 前端恢复窗口 | 自首次提交起最多10分钟；仅用户手动原键原Blob，重放不重置窗口 |

登录、权限、CSRF及基础输入检查失败不占记录。已受理成功或终态失败都缓存，不能因错误自动换键。访问到期记录时也应清除，不在30分钟后继续返回文字；定时清理作为兜底。先处理已有键，再检查新键容量。每用户1个、全局1个实际进行中及每用户每分钟10个新请求的资源限制保留。

内存方案不保证跨重启或记录过期后的去重，30分钟不是7天墓碑。D1重启由mxy人工协调：暂停提交→停止或确认ASR旧任务结束→重启服务→所有演示页面刷新并废弃旧请求。不承诺Java重启前端自动发现并阻止旧请求重发；自动保障属于E1。

页面刷新/退出/换账号清理音频和文字，不自动重发；前端10分钟到期清除恢复材料并提示，不能自动换键。缓存不保留音频Blob，仅保留指纹、状态和必要结果。用户音频只内存，不写multipart/代理临时文件、浏览器持久存储或普通日志；模型文件允许落盘。私人录音及凭据不默认上传GitHub。

## 5. Java—Python内部接口（冻结两个）

### GET /health/ready

200表示模型预热完成；503表示未加载完成或需要人工恢复。就绪不等于空闲，有任务时新转写仍429。只返回本机最少就绪信息，不增加查询或取消接口。

### POST /internal/asr/transcriptions

Header：Authorization: Bearer <内部凭据>；X-ASR-Timeout-Ms为Java剩余处理时间，整数1–120000。multipart：requestId、locale=zh-CN、唯一audio。凭据只在Java/Python配置，不入前端、仓库或普通日志。

成功HTTP200闭合结构：
```json
{"requestId":"11111111-1111-4111-8111-111111111111","text":"暂停当前任务","durationMs":1840,"modelRevision":"部署时冻结的模型版本"}
```

错误固定结构，能确认合法ID则返回它，否则null：
```json
{"requestId":null,"code":"ASR_UNAVAILABLE","message":"识别服务暂不可用"}
```

| Python内部错误 | Java公共响应 |
|---|---|
| ASR_BUSY | 429 VOICE_RATE_LIMITED |
| ASR_UNAVAILABLE | 503 VOICE_PROVIDER_UNAVAILABLE |
| ASR_TIMEOUT | 504 VOICE_TRANSCRIPTION_TIMEOUT |
| ASR_NO_SPEECH | 422 VOICE_NO_SPEECH |
| ASR_AUDIO_TOO_LARGE | 413 VOICE_AUDIO_TOO_LARGE |
| ASR_AUDIO_TOO_LONG | 413 VOICE_AUDIO_TOO_LONG |
| ASR_AUDIO_FORMAT_UNSUPPORTED | 415 VOICE_AUDIO_FORMAT_UNSUPPORTED |
| ASR_TRANSCRIPT_TOO_LONG | 422 VOICE_TRANSCRIPT_TOO_LONG |

Python业务错误HTTP采用表内对应状态；内部鉴权可401/403但正文固定code=ASR_UNAVAILABLE，Java作为部署错误返回503。非法内部响应、未知错误或关联ID不匹配返回502 VOICE_PROVIDER_INVALID_RESPONSE，不能展示成功。成功ID必须完全匹配；合法错误的ID可null，非空则必须匹配。模型revision和字段范围同样校验。内部参数非法应受控拒绝并按固定结构报告，不得启动推理，不能泄露堆栈。

Java公共层另处理400 VOICE_INVALID_REQUEST/VOICE_AUDIO_EMPTY、401 UNAUTHORIZED、403 FORBIDDEN/CSRF_INVALID、408 VOICE_UPLOAD_TIMEOUT、409幂等错误、503 VOICE_INTELLIGENCE_DISABLED。网络不可达503；等待超时504。Retry-After整数秒；处理中同键固定2秒，其他限流按实际窗口返回。

## 6. 期限与单任务

Java完整接收上传后开始120秒总处理期限；前端从提交起140秒，上传10秒。Java调用前算剩余时间，HTTP等待不超过剩余时间；剩余已耗尽不调用。Python从收到内部请求头起按剩余时间计时，包含读取、解码、推理，不重置为120秒。

busy覆盖整个处理过程，不仅模型调用。HTTP超时或浏览器取消不释放仍在运行的任务；只有实际结束或旧进程确认退出后才释放容量，不能启动第二个推理。Java返回超时后迟到成功不得覆盖已缓存终态。Java与Python都禁止自动重试内部推理调用。

D1允许人工重启独立ASR恢复，必须确认旧进程退出再启动新实例，不能误停算法Runner。页面“取消”仅停止等待，不声称模型已取消。ready与busy分别检查。

## 7. D01–D12清单

初始NOT_RUN；mxy执行、nly复核关键演示。记录机器、浏览器版本、commit、模型指纹、参数、样本时长/摘要、requestId、实际响应、调用次数及脱敏证据。真实识别与fixture证据分开。

| ID | 场景与标准 |
|---|---|
| D01 | 不启动仿真，localhost浏览器真实录音→Java→本地模型→可编辑文字 |
| D02 | 拒绝麦克风，提示明确，无空上传 |
| D03 | 静音422，无伪造成功文字 |
| D04 | 未就绪/不可达/需恢复503；ready和busy分开验证 |
| D05 | 重复点击、同键处理中/完成/冲突；1000容量满已有键可读；30分钟过期及每分钟清理，处理中不清理；前端10分钟恢复不续期 |
| D06 | 退出/取消/切换账号清理与迟到隔离；人工重启协调刷新废弃旧请求，不承诺自动检测 |
| D07 | 说“停止任务”只显示文字，proposal/execution/command新增0 |
| D08 | 401/403/CSRF拒绝不调用模型、不占记录；返回/重放权限复核 |
| D09 | WebM/Opus及MP3；1字节至5MiB和总6MiB；58秒软停止尾帧/60秒真实边界；500码点完整显示 |
| D10 | 120/140/10秒及剩余时间；busy覆盖读/解码/推理；无自动重试；内部错误/ID；安全人工恢复 |
| D11 | 缓存模型后离线识别；音频不落盘、秘密/正文不入普通日志、终态内存清理 |
| D12 | 原P0手工与Unity兼容，ASR开关/重启不误停算法Runner |

时间边界可用可控时钟和故障注入；真实录音、离线识别必须实际模型。D01、D07、D12及人工重启演示由nly复核。D1通过只宣布首轮演示完成，不把未做E1用例标PASS。

## 8. 每人首轮工作清单

### nly：前端

独立本地语音识别入口，无仿真可用；隐藏意图解析。指定Chrome/Edge版本及WebM/Opus，58秒软停止/尾帧处理/真实上限提示，动态CSRF与三标识，140秒等待和主动取消。完整显示500码点并编辑。首次提交10分钟手动同键原Blob恢复，遵守Retry-After；卸载/退出/换用户清理，迟到隔离。报告本次测试及构建，不用历史64项代替本轮结果。

### nly：Python

独立服务实现两个内部接口，启动加载预热模型，mxy机候选small CPU INT8/4线程。冻结模型/依赖指纹、配置凭据、ready/busy、错误结构和剩余期限。内存受限解码/时长，单任务覆盖完整处理，无自动重试。提供可确认ASR旧PID退出的人工停止/启动步骤，不影响算法Runner。交付版本、变量名、实际codec和测试报告，不上传模型/秘密/私人音频。

### nly：Unity与复核

无新增ASR代码，保留构建版本；检查原手工控制/显示、ASR重启不误停。复核mxy的真实浏览器D01、不触发控制D07、兼容D12及重启流程，记录独立复核结论。

### mxy：Java与部署

维护公共契约/Schema/样例与内部适配；ADMIN/CSRF/输入及返回前权限，真实错误映射/ID校验。核查能否复用持久幂等，否则按1000条/30分钟/每分钟清理实现内存方案；已有键优先、终态失败也缓存、活跃不清理。上传10秒/处理120秒/剩余等待，不自动重试。部署同机Java/Python/浏览器，localhost代理与Cookie/CSRF对齐，密钥和音频不落盘。mxy统一人工重启协调。保持P0基线，不实现意图提案关联。

### mxy：D1测试与证据

执行全部D01–D12及子边界，检查真实推理次数、缓存失败、容量边界、30分钟清理、10分钟窗口、人工重启和隐私。记录部署机而非nly机性能；真实模型与fixture分层。维护46项E1实际状态，提交nly复核后归档。可控时钟验证保留时间，但真实录音不能用Mock代替。

## 9. 并行与交接

M0按本最终稿同步文档、Schema和接口消费者；M1 nly前端/Python与mxy Java/测试并行；M2 Java接真实ASR再浏览器；M3全部D项通过及复核后演示；M4 E1继续待办。共享契约由mxy主编，nly确认，不互相覆盖分支。

mxy沿用mxy/p1-backend-20260923，主写backend/部署/契约及测试报告；nly沿用个人P1分支，主写frontend/asr-service，Unity只修实际兼容缺陷。每次交接给出commit、版本、启动/关闭、变量名无秘密值、模型/浏览器标识、测试实际通过/失败/阻塞数、证据及未完成项。

重启操作单：暂停所有页面提交→确认ASR旧任务结束或停止独立进程→确认PID退出→重启目标服务→检查ready/配置→全部页面刷新重新登录并废弃旧请求→恢复演示。不能仅重启Java后继续旧页面恢复，也不承诺自动发现重启。

E1完整46项以配套规划v1.3第8节为权威表；长期持久化/跨重启/五格式/60条统计仍待办。本文是最终分工与约定，不声称任何尚未执行的测试已通过。
