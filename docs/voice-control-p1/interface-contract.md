# 语音识别与意图解析 P1 供应商无关接口契约（草案 v1）

状态：前端可独立实现、后端待评审；本文件不表示真实 ASR/LLM 已接入。

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
