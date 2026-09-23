# D2 本机真实浏览器联调证据（2026-09-24）

## 环境

- 分支：`mxy/p1-intent-20260923`
- 验证起点：`e1544144e11f140cc89b0a40ef922a0c7739ba51`
- 前端：`http://localhost:5175/?workspace=simulation`
- Java 后端：`http://127.0.0.1:18081`
- Python ASR：`http://127.0.0.1:18082`
- 数据库：本机 MySQL 隔离库 `uav_usv_p0_integration`，Flyway V20
- 算法执行端：真实 Python Runner
- 展示端：Unity WebGL

本文件不包含账号密码、内部令牌、录音或模型文件。

## 独立文字解析

通过登录后的前端代理和真实 Java 接口验证 9 个输入：

| 输入类别 | 预期结果 | 结果 |
| --- | --- | --- |
| START / PAUSE / RESUME / STOP | `CANDIDATE` 及匹配动作 | PASS（4/4） |
| 否定句 | `NOT_ACTIONABLE / NEGATED_ACTION` | PASS |
| 多动作歧义 | `NEEDS_CLARIFICATION / AMBIGUOUS_ACTION` | PASS |
| 无支持动作 | `NEEDS_CLARIFICATION / NO_SUPPORTED_ACTION` | PASS |
| 不支持能力 | `UNSUPPORTED / UNSUPPORTED_CAPABILITY` | PASS |
| 单设备指令 | `UNSUPPORTED / UNSUPPORTED_TARGETING` | PASS |

解析器返回 `provider=local-rules`、`model=rules-v1`。解析阶段没有直接创建 execution，也没有直接调用 Runner。

## 真实浏览器闭环

操作链路：

`输入“开始任务” → 解析指令 → START 候选 → 生成待确认提案 → 人工点击“确认执行” → Runner SUCCEEDED → Unity REPORTED_APPLIED`

页面最终显示：

- 运行状态：`RUNNING`
- 算法结果：`SUCCESS`
- 展示状态：`Unity 已应用`

关联证据：

| 字段 | 值 |
| --- | --- |
| algorithmRunId | `1790205421511` |
| runtimeRef | `4678880a-0219-422d-bff9-84385433fb2b` |
| runtimeGeneration | `ec4511f8-2b41-446d-9a90-9d87e74c14b0` |
| interpretationId | `7ccf8266-6e59-4df4-8978-2189d0b3007c` |
| proposalId | `d59e096e-9025-4761-945d-dd65e02a2fa2` |
| executionId | `bf9f9cf9-8930-4af3-ba6c-81a908642b0b` |
| commandId | `367a0550-a8cc-4a4d-a9f6-a99a161958ad` |
| bindingId | `25cb584c-3b4f-45bd-abc5-23b5ef187a63` |

数据库记录显示 proposal 为 `CONFIRMED` 且保留 `interpretationId`；execution 为 `SUCCEEDED / SUCCESS / REPORTED_APPLIED`。Runner 事件 1 为 `ACCEPTED`，事件 2 为 `SUCCEEDED`，最终 `runtimeState=RUNNING`、`stateVersion=1`，六台任务设备与冻结计划一致。

## 联调中发现并修复的问题

前端此前使用数组作为 Vue `watch` 的返回值。运行上下文轮询会替换同值对象，导致监听回调反复执行，文字输入及解析结果被清空。修复后，重置条件只由操作员、权限、`runtimeRef` 或 `runtimeGeneration` 的实际变化触发；同一代次的 `contextVersion` 刷新不再清空输入，提案时仍由后端执行当前版本校验。

验证结果：

- `VoiceIntelligenceInput.spec.ts`：11/11 PASS
- `npm run build`：PASS
- 输入后等待超过一次上下文轮询：内容保持，解析按钮仍可用
- 真实浏览器候选、提案、人工确认、Runner 和 Unity 闭环：PASS

