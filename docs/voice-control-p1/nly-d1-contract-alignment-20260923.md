# nly D1契约对齐与推送交接

日期：2026-09-23。对照用户最终稿规划v1.3/分工v1.1，以及mxy远端实现425a96c。本文优先于nly首轮交接中标为“待确认”的旧说明；不代改mxy Java实现或虚报整体验收。

## 已对齐的接口

公共接口POST `/api/voice/intelligence/transcriptions`，三标识一致，动态CSRF，登录ADMIN；不调用意图接口或生成控制记录。前端固定接入算法仿真页面右侧“语音控制”面板，不设独立页面或导航；环境开关`VITE_VOICE_ASR_ONLY=true`，默认仍关闭。

格式仅WebM/Opus与MP3；文件1字节至5MiB、总multipart6MiB；58秒软停止、完整实际音频≤60000ms；最多2声道、48kHz、禁止视频；文字1–500 Unicode码点。不支持其他格式的声明留E1。

Java上传10秒、处理120秒；前端从提交开始等待140秒；Python使用Java剩余期限，读请求/解码/推理占同一槽位，超时不提前释放仍在运行的任务。

Python两接口：GET `/health/ready`、POST `/internal/asr/transcriptions`；内网Bearer、Content-Length、X-ASR-Timeout-Ms，闭合结构与最终稿一致。425a96c使用ofByteArray发送，已满足Content-Length。非法内部参数改为503 ASR_UNAVAILABLE（原400草案撤回）；鉴权401 ASR_UNAVAILABLE在Java映射503。busy为429 ASR_BUSY及Retry-After:2。

## 公共错误码核对表

| HTTP | code | 主责 |
|---|---|---|
|400|VOICE_INVALID_REQUEST / VOICE_AUDIO_EMPTY|Java入口|
|401/403|UNAUTHORIZED / FORBIDDEN / CSRF_INVALID|Java权限|
|408|VOICE_UPLOAD_TIMEOUT|Java上传|
|409|IDEMPOTENCY_CONFLICT / VOICE_REQUEST_IN_PROGRESS|Java幂等；处理中Retry-After:2|
|409|VOICE_REQUEST_OUTCOME_UNKNOWN|已有约定；重启保护仍待mxy实现，nly前端已禁止原请求重试|
|409|VOICE_REQUEST_EXPIRED|保留既有错误兼容；D1内存过期不声称已有持久墓碑|
|413|VOICE_AUDIO_TOO_LARGE / VOICE_AUDIO_TOO_LONG|Java/Python|
|415|VOICE_AUDIO_FORMAT_UNSUPPORTED|Java/Python|
|422|VOICE_NO_SPEECH / VOICE_TRANSCRIPT_TOO_LONG|Python识别结果|
|429|VOICE_RATE_LIMITED|Java容量/速率、Python忙|
|502|VOICE_PROVIDER_INVALID_RESPONSE|Java内部响应校验|
|503|VOICE_INTELLIGENCE_DISABLED / VOICE_PROVIDER_UNAVAILABLE|Java开关/服务/配置|
|504|VOICE_TRANSCRIPTION_TIMEOUT|处理超时|

## 缓存与十分钟恢复

已约定Java内存1000条（含活跃及终态）；终态完成后30分钟删除，不因重放续期；每分钟清理且访问时清理过期项；不得驱逐活跃项；容量满拒绝新键但允许已有键核对。该实现归mxy，nly未复制第二套缓存到Python。

前端首次提交起最多10分钟保留原键/Blob，手动重试不续期；遵守Retry-After；到期自动清除恢复材料；取消只终止浏览器等待；刷新/卸载/退出/换账号均清理，绝不自动重发或换键。Python不做业务幂等、不自动重试、不保存音频。

## 必须解决的Java重启旧键风险（代码核查，未冒充故障实测）

425a96c的AsrService使用进程内HashMap；超时保护occupied/quarantined也在内存。Java重启后无法分辨“旧键”与“从未见过的新键”。旧页面手动重试、HTTP重放都可能再次调用Python。前端禁自动重试、10分钟限制或仅确认Python空闲均不能消除此风险。

原D1最终稿允许人工协调刷新，但此次反馈明确要求避免重启静默重新推理。因此不能将原人工操作单宣称为自动保障，也不能把D重启用例标PASS。

建议mxy采用**最小持久受理标记**，不必先实现完整E1文字库：

1. 在调用Python之前，事务提交userId/endpoint/requestId唯一键、内容摘要、受理时间与状态；不保存原音频或文字。
2. 重启后先查标记，再判断是否新请求。同键不同摘要仍409冲突；同键存在但没有可用原结果，返回409 VOICE_REQUEST_OUTCOME_UNKNOWN，不启动推理。
3. 即使任务完成也保留标记：内存结果因重启丢失，不能把此前已完成的键再执行一次。新标记写入失败则拒绝调用，不能降级为无保护推理。
4. mxy与团队明确标记保留期和到期语义后更新机器Schema/清单。建议7天以沿用已有墓碑方向；这属于本次补强提议，尚未实现或冻结。不能宣称无限期去重。
5. 未落实前仅可受控人工重启演示：禁止重启期间提交、确认旧ASR进程结束、所有页面刷新丢弃旧键；不作为“自动拒绝旧键”的通过证据。

这项由mxy后端实现，不改变冻结Python协议，也不需要前端新增header或查询接口。nly可以提交当前独立交付，但正式重启防重验收须等待后端保护。

## 测试执行和证据边界

- `cd frontend; npm run test; npm run build`：前端D1和既有P0/P1回归。
- `cd asr-service; <venv-python> -m unittest -v test_asr_server`：内部HTTP边界、真实音频编码解码；FakeEngine只用于故障测试。
- `smoke_real.py`：真实模型HTTP样本，说明见asr-service/README.md。输出JSON含私人转写，保留仓库外；模型权重/venv/录音/秘密不提交。
- `requirements-lock-win-py313.txt`：全依赖锁定；`model-manifest.json`：模型四文件SHA256，启动再校验。

待mxy/nly联合补测：

1. D01/02/03/09：mxy localhost真实浏览器、麦克风权限、58秒尾帧/60秒解码、静音、500码点。
2. D05：1000容量、30分钟/每分钟清理、失败终态缓存、10分钟不续期；核对实际模型调用次数。
3. D06新增重点：受理中/完成后分别重启Java，重新POST原键原音频均不得增加推理次数；旧键改内容拒绝；新键在安全恢复后可用。当前NOT_VERIFIED，且已知仅内存实现不足。
4. D07/08/10/11/12：无新增控制记录、动态权限、busy/超时、全链路无音频落盘、实际阻断外网以及Unity/P0兼容。

nly本机HTTP结果和单元测试不能替代上述mxy部署机验收。后端完整测试由mxy负责，不修改其代码以掩盖边界缺口。
