# 语音识别与意图解析 P1 供应商无关接口契约（后端对齐版 v1.1）

状态：后端实施约定已整理，待前端确认差异后共同冻结；接口尚未实现，不表示真实 ASR/LLM 已接入。基于前端 77182de 与 P0 42ed66a。第 8 节细化并优先于前述简写约定。

## 1. 安全边界

- 浏览器只访问平台后端，不直接访问任何模型供应商，也不持有供应商密钥。
- ASR 和意图解析只产生可编辑文字或候选意图，不能直接调用 Python Runner 或 Unity。
- 候选意图必须继续进入现有 P0 的“读取最新上下文 → 创建冻结提案 → 用户确认 → 执行”流程。
- `allowedActions`、`availableDeviceCodes` 和 `runtimeContext` 都是解析提示，后端不得将其视为可信授权信息。
- 后端创建提案时仍需重新校验用户权限、运行代次、状态版本、能力和设备集合。
- P1 暂时只允许 `START`、`PAUSE`、`RESUME`、`STOP`。单设备控制、攻击、围捕和撤退不得降级为整队动作。

## 2. 通用约定

两个接口均要求已登录会话，并携带：

| 项 | 约定 |
|---|---|
| `X-Request-ID` | 小写 UUID，与请求体或表单中的 `requestId` 相同 |
| `Idempotency-Key` | 与 `requestId` 相同；相同请求重放返回相同结果，不得重复计费调用 |
| CSRF Header | 使用 `/api/auth/csrf` 返回的动态 headerName 和 token |
| 响应 | 复用平台 `{code,message,data,timestamp}` 包装 |
| 缓存 | 响应必须包含 `Cache-Control: no-store` |
| 请求变更 | 同一幂等键对应不同音频摘要或不同 JSON 时返回 `409 IDEMPOTENCY_CONFLICT` |

模型名称、供应商原始错误、密钥和供应商请求体不得透传到前端日志。响应中的 `provider`、`model` 只是审计标签，前端不能依赖其具体值进行业务分支。

## 3. 音频转文字

`POST /api/voice/intelligence/transcriptions`

内容类型为 `multipart/form-data`，浏览器必须让运行时生成 boundary，不能手工固定 `Content-Type`。

| 字段 | 类型 | 约束 |
|---|---|---|
| `requestId` | string | 小写 UUID |
| `locale` | string | P1 固定 `zh-CN` |
| `audio` | binary | 1 B 至 5 MiB |

支持的基础 MIME：`audio/webm`、`audio/ogg`、`audio/mp4`、`audio/wav`、`audio/mpeg`。允许携带 codec 参数，但服务端按分号前的基础 MIME 判断。

成功时 `data` 使用 Schema 中的 `Transcript`：

```json
{
  "requestId": "11111111-1111-4111-8111-111111111111",
  "text": "暂停当前任务",
  "locale": "zh-CN",
  "durationMs": 1840,
  "provider": "configured-backend",
  "model": "active-revision"
}
```

前端超时基线为 20 秒。超时或取消后不得自动使用新幂等键重发付费调用；是否重试由用户明确触发。

## 4. 文字解析意图

`POST /api/voice/intelligence/interpretations`

内容类型为 `application/json`，请求定义为 `InterpretationRequest`。`runtimeContext` 可以为 `null`，支持前端在后端实例未启动时独立验证解析交互。

解析结果只允许以下四类：

- `CANDIDATE`：得到一个 P0 候选动作，可以进入提案创建。
- `NEEDS_CLARIFICATION`：没有动作或一句话出现多个动作，需要用户重述。
- `UNSUPPORTED`：动作/目标超出当前能力，不得创建提案。
- `NOT_ACTIONABLE`：否定表达等不应执行的输入，不得创建提案。

候选响应示例：

```json
{
  "status": "CANDIDATE",
  "requestId": "11111111-1111-4111-8111-111111111111",
  "intent": "MISSION_PAUSE",
  "action": "PAUSE",
  "normalizedText": "暂停当前任务",
  "confidence": 0.96,
  "provider": "configured-backend",
  "model": "active-revision"
}
```

前端超时基线为 12 秒。前端只接受 requestId 与当前请求完全一致且满足 Schema 的响应；迟到、串线或未知字段响应不进入提案流程。

## 5. 错误与 HTTP 状态

| HTTP | 典型错误码 | 含义 |
|---:|---|---|
| 400 | `VOICE_INVALID_REQUEST`、`VOICE_AUDIO_EMPTY` | 字段或内容错误 |
| 401/403 | 平台既有认证/权限错误 | 未登录、撤权或 CSRF 失败 |
| 409 | `IDEMPOTENCY_CONFLICT`、`VOICE_CONTEXT_CHANGED` | 幂等冲突或运行上下文失效 |
| 413 | `VOICE_AUDIO_TOO_LARGE` | 音频超过 5 MiB |
| 415 | `VOICE_AUDIO_FORMAT_UNSUPPORTED` | MIME 不支持 |
| 429 | `VOICE_RATE_LIMITED` | 用户或供应商限流，允许携带 `Retry-After` |
| 502/503 | `VOICE_PROVIDER_UNAVAILABLE` | 上游服务不可用 |
| 504 | `VOICE_TRANSCRIPTION_TIMEOUT`、`VOICE_PARSE_TIMEOUT` | 后端等待供应商超时 |

歧义、否定、不支持能力属于正常解析结果，使用 HTTP 200，不使用 4xx 表达。

## 6. 隐私、审计与留存

- 前端不把音频写入 `localStorage`、Pinia 持久化或普通运行日志。
- 后端普通日志只记录 requestId、用户、耗时、结果分类、供应商审计标签和错误码，不记录原始音频、完整识别文本或密钥。
- 原始音频应以内存流处理并在请求结束后释放；如因测试或审计必须留存，需要单独审批、加密和明确过期时间。
- 供应商调用预算、并发、速率和最大录音时长由后端集中控制，不能依赖浏览器限制。

## 7. 验收边界

当前前端实现和本目录 Schema 只能证明接口边界与交互准备完成。正式启用还需后端评审并实现接口、选择供应商、配置凭据和预算，再完成真实浏览器、网络失败、撤权及端到端提案验收。


## 8. 后端实施约定 v1.1

### 8.1 权限与开关

两个接口均仅允许启用中的 ADMIN，逐次读取当前账号权限，不能只信任旧会话角色。每次重放也重新校验权限。沿用 401 UNAUTHORIZED、403 FORBIDDEN、403 CSRF_INVALID。P1 独立开关 `app.voiceintelligence.enabled` 默认 false；关闭返回 503 VOICE_INTELLIGENCE_DISABLED。该开关不自动开启 P0。检查顺序：认证/CSRF、当前权限、开关、格式/大小、幂等、上下文、限流预算、供应商。超大请求可由入口提前返回 413。

### 8.2 字段、音频及响应

- 两个路径及现有 JSON 字段不变，未知字段拒绝。三个请求标识必须一致，否则 400 VOICE_INVALID_REQUEST。
- 转写表单仅 requestId、locale、audio；Schema 的 TranscriptionRequestMetadata 是后端归一化校验对象，不是额外表单字段。
- 单文件 1–5242880 字节，单次 multipart 请求最大 6 MiB，最多一个 audio 部件。实际时长大于 0 且不超过 60000 ms。检测容器、codec 和可解码性，不能只相信 MIME/扩展名。解码失败或无法确认时长返回 415 VOICE_AUDIO_FORMAT_UNSUPPORTED；超时长返回 413 VOICE_AUDIO_TOO_LONG；空音频 400 VOICE_AUDIO_EMPTY。
- 基础 MIME 保持原五种；不支持的 codec 返回 415，具体 codec 可用性必须由选定适配器测试，不宣称所有 codec 均支持。禁止从用户提供的 URL 下载音频。
- Transcript.durationMs 必须为服务端实际测量的 1–60000 整数，不再允许 null。无可识别语音返回 422 VOICE_NO_SPEECH。
- Transcript.text 最长 500，InterpretationRequest.text/normalizedText 最长 200；超过 200 的识别文字由用户编辑后解析，不静默截断。纯空白输入 400；字符串长度按 Unicode 码点计算。
- 成功响应 HTTP 200，code=SUCCESS；四类解析结果保持不变。provider/model 为不含真实供应商配置的公开审计别名。测试适配器固定 provider=test-fixture、model=fixed-v1，仅隔离环境允许；不能将任意输入统一伪装成成功动作。
- 所有响应 Cache-Control:no-store；合法 requestId 在 X-Request-ID 回显。错误 data=null，不回显文本、供应商请求或密钥。

### 8.3 幂等、超时和取消

- 唯一范围为 userId + endpoint + Idempotency-Key，两个接口不能共享一次请求 ID。标识沿用前端小写 UUID。服务端原子占位后才能调用供应商。
- JSON 指纹使用 RFC 8785 规范化后的完整请求，不做 Unicode 归一化；音频指纹由原始字节 SHA256、locale、规范化基础 MIME 构成，不包含 boundary 和文件名。摘要由后端计算。
- 完整结果保留 24 小时；期满去除文本结果，幂等键/摘要墓碑保留 7 天，返回 409 VOICE_REQUEST_EXPIRED，不能偷偷重复计费。超过 7 天为新请求窗口，客户端仍不得自动换键重试。
- 同键不同内容 409 IDEMPOTENCY_CONFLICT；同键处理中 409 VOICE_REQUEST_IN_PROGRESS，Retry-After:2。完成后同键同内容重放相同业务响应及原 timestamp，不再次调用供应商；权限或运行代次失效时安全拒绝优先。
- 从接收完成请求起，ASR 总处理期限 15 秒，解析 8 秒（包含队列与校验）；前端仍分别 20/12 秒。上传另设 10 秒入口期限，超限 408 VOICE_UPLOAD_TIMEOUT。各部署层超时需对齐。
- 后端等待超时返回原 504 错误并保存终态；迟到结果不得覆盖。发生崩溃/调用结果未知且无法从供应商可靠查询时，409 VOICE_REQUEST_OUTCOME_UNKNOWN，不自动补发。每键至多发起一次平台调用意图，但不承诺上游计费的 exactly-once。
- 浏览器取消只停止等待，不等同供应商取消成功。后端尽力取消并记录结果；原键可用于恢复查询（重发相同 POST），不可自动创建新键。未授权、格式校验失败不占位；供应商调用后的失败必须占位留档。

### 8.4 上下文及 P0 提案关联

runtimeContext=null 允许 ADMIN 进行独立文字解析；候选不是执行许可。有上下文时在调用前及返回结果前检查运行归属、runtimeRef、runtimeGeneration、contextVersion；失效返回 409 VOICE_CONTEXT_CHANGED。allowedActions 和设备列表只作提示，以后端权威能力和设备集合为准。模型输出严格按 Schema 和四动作白名单校验，不支持单设备和多动作自动拆分；输出结构非法返回 502 VOICE_PROVIDER_INVALID_RESPONSE。

为避免改动 P0 JSON Schema，创建 P0 提案时增加可选 HTTP 头 X-Voice-Interpretation-ID，值为成功解析的 requestId。手工 P0 请求无需此头。后端要求来源属于当前用户、endpoint=interpretations、状态=CANDIDATE、结果未过期，且候选 action/intent 与提案一致；失败 409 VOICE_INTERPRETATION_INVALID。该头参与 P0 提案幂等摘要，不能同键替换来源。来源与 proposalId 在同一事务存储，再通过既有 proposalId→executionId→commandId 关联。后端仍按最新上下文重新校验并冻结提案；有上下文来源必须匹配同一 runtimeRef/generation，null 来源在创建时绑定最新合法上下文。不能把客户端传来的 requestId 当作已验证来源。

解析并不自动创建提案，不自动确认，不改变 Runner/Unity 协议。前端需新增此头及撤权/代次变更后的候选清理；本关联机制尚待实现，不得报告为已支持。

### 8.5 限流、预算、隐私

初始隔离默认值：每用户最多 2 个进行中请求、每接口每分钟 10 个新请求、全局最多 4 个供应商调用；重放不占供应商配额，但仍受入口保护。限流 429 VOICE_RATE_LIMITED、Retry-After 为整数秒。真实供应商预算必须显式配置，预算未配置时禁止真实调用（503 VOICE_PROVIDER_UNAVAILABLE），耗尽 429 VOICE_BUDGET_EXCEEDED；具体金额和模型由团队另定。

日志保留 30 天，仅 userId、requestId、endpoint、耗时、分类、错误码、公开别名及关联 ID；幂等完整响应可能含识别文本，限制访问并加密保存，24 小时清理；摘要墓碑 7 天。原始音频禁止持久化；multipart 必须禁用默认磁盘落地，采用受限内存，处理完成/失败释放。该数据处理约定须在实现和部署测试中验证，不能用文档代替证据。

### 8.6 前端需确认清单

- 录音上限 60 秒，转写 durationMs 非空；大于 200 字的文本编辑提示。
- 新错误码、处理中同键重试、结果未知不换键自动重发。
- P0 提案 X-Voice-Interpretation-ID 关联头。
- ADMIN 权限与独立开关，测试 provider 明确显示。

以上为本次建议采用的实施基线，前端确认前不称为双方已冻结。模型、codec 实测支持及具体预算不阻塞契约测试，但阻塞真实供应商启用。
