# UAV-USV P1-ASR 规划调整与接口契约测试设计 v1.3

配套分工v1.1。

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

D1只验收D01–D12。D1现增加最小受理墓碑用于重启防重；E1完整结果持久化、五格式和统计评测以及原46项完整用例继续待办，不能因D1通过标记E1完成。规划统一引用v1.3、分工统一引用v1.1，旧v1.2仅历史来源。没有新增查询、取消或复杂任务管理接口。

## 3. 公共接口与音频

POST /api/voice/intelligence/transcriptions，multipart由浏览器自动生成boundary。字段requestId小写UUID、locale=zh-CN、唯一audio；X-Request-ID、Idempotency-Key均等于requestId；动态CSRF头保留。仅当前启用ADMIN，返回前及重放复核权限。登录/权限/CSRF/基础字段、大小限制不可省略；ASR不要求runtimeRef。

D1明确支持部署清单指定版本Chrome/Edge的WebM/Opus与MP3文件测试；浏览器版本在部署时记录并冻结。其他格式留E1，不在页面宣称支持。服务端验证真实容器、codec、可解码性，不只信任MIME。拒绝视频轨道、超过2声道或48kHz输入；受限转换16kHz单声道，最多960000采样点。

大小为**1字节至5MiB（5242880字节）**；完整multipart≤6MiB。页面约58秒软停止，等待最终编码Blob；实际文件上限60000ms。计时与编码尾帧可能有延迟，软停止不能保证所有文件合规；实际时长由后端解码测量并向上取整毫秒。超限413 VOICE_AUDIO_TOO_LONG并提示重录，不裁剪、不伪造时长。界面明确“最长录制约58秒，文件上限60秒”。

文本最多500个Unicode码点，完整展示，不套用意图解析200字限制。无语音422 VOICE_NO_SPEECH，超长422 VOICE_TRANSCRIPT_TOO_LONG。成功HTTP200，外层{code:SUCCESS,message,data,timestamp}，data为requestId、text、locale、durationMs、provider=local-asr、model=冻结公开别名；错误data=null。no-store，合法ID回显X-Request-ID；无秘密、堆栈或内部路径。

## 4. D1幂等最终规则

完整结果优先使用内存方案，同时持久保存最小受理墓碑，防止Java重启后对旧键重复推理。

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

内存完整结果保留30分钟；最小墓碑保留7天，仅含用户、接口、请求ID、内容指纹及受理/过期时间。Java重启后旧键同内容返回409 VOICE_REQUEST_OUTCOME_UNKNOWN，改内容返回409 IDEMPOTENCY_CONFLICT，禁止再次推理；7天过期后进入新受理窗口。该方案不恢复旧文字，完整结果跨重启恢复仍属于E1。

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
| D06 | 退出/取消/切换账号清理与迟到隔离；重启后旧键由7天墓碑拒绝重复推理，页面仍刷新废弃旧请求 |
| D07 | 说“停止任务”只显示文字，proposal/execution/command新增0 |
| D08 | 401/403/CSRF拒绝不调用模型、不占记录；返回/重放权限复核 |
| D09 | WebM/Opus及MP3；1字节至5MiB和总6MiB；58秒软停止尾帧/60秒真实边界；500码点完整显示 |
| D10 | 120/140/10秒及剩余时间；busy覆盖读/解码/推理；无自动重试；内部错误/ID；安全人工恢复 |
| D11 | 缓存模型后离线识别；音频不落盘、秘密/正文不入普通日志、终态内存清理 |
| D12 | 原P0手工与Unity兼容，ASR开关/重启不误停算法Runner |

时间边界可用可控时钟和故障注入；真实录音、离线识别必须实际模型。D01、D07、D12及人工重启演示由nly复核。D1通过只宣布首轮演示完成，不把未做E1用例标PASS。

## 8. E1完整工程保留清单

本节明确为E1而非D1前置。原46条保持待测，D1证据可复用相同子项，但不能自动视为整条E1通过。D1只实现7天最小受理墓碑和重启防重复推理；24小时加密结果、旧文字跨重启恢复、30天审计清理、自动worker故障恢复、五种音频格式和统计评测仍属于E1。

| ID | 场景 | 操作/输入 | E1预期 |
|---|---|---|---|
| A01 | 未登录上传 | 无登录会话 POST | 401 UNAUTHORIZED；模型调用为0 |
| A02 | 普通用户上传 | 非 ADMIN 会话及有效CSRF | 403 FORBIDDEN；调用为0 |
| A03 | CSRF失效 | ADMIN使用错误或缺失CSRF | 403 CSRF_INVALID |
| A04 | 运行中撤权 | 模型处理期间禁用账号或撤销ADMIN | 结果返回前复核，403；不泄露文字 |
| A05 | 跨账号同键 | 两个账号使用同一UUID | 幂等空间独立；不能获得对方结果 |
| A06 | 功能关闭 | 关闭ASR后上传 | 503 VOICE_INTELLIGENCE_DISABLED；P0手工控制可用 |
| C01 | 三个标识一致 | 表单及两个头使用相同小写UUID | 合法请求可受理 |
| C02 | 标识缺失或不同 | 分别缺失及改写请求标识 | 400 VOICE_INVALID_REQUEST；调用为0 |
| C03 | multipart边界 | 真实浏览器自动生成boundary | 成功读取唯一audio部件 |
| C04 | 空和超大文件 | 0字节、5MiB+1、总请求6MiB+1 | 分别400 VOICE_AUDIO_EMPTY、413 VOICE_AUDIO_TOO_LARGE |
| C05 | MIME与文件不符 | 文本伪装audio/webm；codec不支持 | 415 VOICE_AUDIO_FORMAT_UNSUPPORTED |
| C06 | 真实五种容器 | WebM/Opus、Ogg/Opus、MP4/AAC、WAV/PCM、MP3各真实录音 | 逐项解码并转写；未通过的格式不得宣称支持 |
| C07 | 时长边界 | 有效短音频、60000ms、60001ms | 前两者允许，后者413 VOICE_AUDIO_TOO_LONG |
| C08 | 字段与重复部件 | 未知表单字段、两个audio、非zh-CN | 400 VOICE_INVALID_REQUEST |
| C09 | 输出结构 | 实际成功响应 | SUCCESS包装、durationMs为1–60000整数、无未知字段、no-store |
| C10 | 静音和无语音 | 静音、空白噪声录音 | 422 VOICE_NO_SPEECH；不展示幻觉文字为有效指令 |
| C11 | 输出长度 | 转写超过500码点 | 422 VOICE_TRANSCRIPT_TOO_LONG；不静默截断 |
| C12 | 解码资源限制 | 异常采样率/声道、损坏容器、解码膨胀 | 受限拒绝；不导致服务耗尽 |
| I01 | 完成后同键重放 | 相同用户/音频/标识POST两次 | 相同业务响应与timestamp；模型只调用一次 |
| I02 | 同键不同音频 | 复用键替换音频字节 | 409 IDEMPOTENCY_CONFLICT |
| I03 | 同键并发 | 同时提交同键相同请求 | 至多一次推理；另一请求409 VOICE_REQUEST_IN_PROGRESS和Retry-After:2 |
| I04 | 处理中取消恢复 | 浏览器取消后页面内原请求重发 | 复用键和Blob；不重复推理 |
| I05 | 刷新恢复边界 | 识别中刷新或卸载组件 | 清除音频/文字，不自动重发；明确结果可能已处理 |
| I06 | 结果过期墓碑 | 可控时钟跨24小时及7天边界 | 24小时清正文；7天内409 VOICE_REQUEST_EXPIRED；不自动重算 |
| I07 | 处理中后端崩溃 | 推理发出后终止Java并重启 | 409 VOICE_REQUEST_OUTCOME_UNKNOWN；禁止自动再调用 |
| I08 | ASR子进程崩溃 | 处理中终止独立ASR worker | 受控失败/未知终态；不影响算法Runner |
| R01 | 推理总超时 | 注入超过120秒处理 | 504 VOICE_TRANSCRIPTION_TIMEOUT；迟到结果不覆盖 |
| R02 | 上传超时 | 持续慢上传超过10秒 | 408 VOICE_UPLOAD_TIMEOUT；音频缓冲释放 |
| R03 | 本机并发限制 | 多个用户同时请求 | 全局1次推理；额外请求429及Retry-After |
| R04 | 单用户速率 | 一分钟内超过10个新请求 | 429 VOICE_RATE_LIMITED；不额外推理 |
| R05 | 模型未就绪 | 启动未完成或模型文件缺失 | 503 VOICE_PROVIDER_UNAVAILABLE；禁止请求时临时下载 |
| R06 | 权限与缓存 | 完成后撤权再重放 | 403而非返回缓存文字 |
| R07 | 服务不可达 | 断开Java与本地ASR服务 | 503 VOICE_PROVIDER_UNAVAILABLE；可恢复提示 |
| B01 | 浏览器实录 | 真人麦克风录制5–15秒中文 | 真实模型返回可编辑文字；非Mock |
| B02 | 麦克风拒绝 | 拒绝麦克风授权 | 友好提示；无空上传 |
| B03 | 录音自动结束 | 达到60秒或切换页面 | 停止采集；卸载清理资源 |
| B04 | 用户切换迟到 | A上传后退出，以B登录 | A迟到文字不进入B页面 |
| B05 | 无算法实例识别 | 不启动仿真，仅打开ASR入口 | 识别可用，不依赖runtime/sceneReady |
| B06 | 不触发控制 | 说出开始/停止等词后完成转写 | proposal/execution/command新增数量均0 |
| B07 | 保留手工P0 | ASR运行时手动四动作及关闭ASR | 手工P0按既有规则工作；不将ASR结果自动送入P0 |
| S01 | 音频不落盘 | 观察请求成功/失败/超时的临时目录与日志 | 无原始音频持久文件、浏览器存储或普通日志文本 |
| S02 | 加密及清理 | 检查结果库加密、24小时/7天/30天清理 | 权限受限且清理入口可执行，有证据 |
| S03 | 完全离线推理 | 模型缓存后阻断外网 | 真实录音仍成功，无云端或遥测依赖 |
| S04 | 资源竞争 | Unity及Runner同时运行时转写 | 记录CPU/RAM/心跳，不因ASR饿死算法进程 |
| Q01 | 准确率评测 | 固定真人录音集与人工参考文本 | 输出CER、术语命中率、噪声分组结果 |
| Q02 | 性能评测 | base/small各相同音频，冷启动和预热分开 | 记录p50/p95、RTF、峰值内存及超时率 |

E1统计集保留60条/3说话人、40安静/10噪声/10术语及单独长录音/静音；参考全文与归一化规则提前冻结，按CER、术语命中、p50/p95、RTF及资源竞争评估。建议目标待导师确认，不能把短样本或120秒操作上限当性能达标。A/B机器分开报告。

实施顺序：按最终稿同步Schema/样例与代码→Java/Python并行→localhost浏览器→D01–D12及nly复核→演示→E1逐步补齐。文档更新不意味着代码、配置或机器Schema已实现；应使用独立提交验证。旧v1.2只留历史。
