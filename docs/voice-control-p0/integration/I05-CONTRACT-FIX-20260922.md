# I05 契约修正与前端对接说明

2026-09-22，按用户确认的口径保留现行 Schema，I05 从 FAIL 更新为 PASS。生产后端逻辑、数据库、Python 和 Unity 不需要修改。

## 统一规则

| 子场景 | 请求条件 | HTTP / code |
|---|---|---|
| I05-a | expectedPlanVersion=2；当前 Schema 只允许 1 | 400 / INVALID_REQUEST |
| I05-b | expectedPlanVersion=1，expectedPlanHash 格式合法但与原提案不一致 | 409 / PLAN_MISMATCH |

先做 Schema 校验，再比较持久化计划。哈希格式错误同属 400。确认和取消均使用上述规则。两种拒绝都必须保持原提案完整快照不变、execution=0、outbox=0、算法管道写入=0。

保持主清单 I05 一行，通过 I05-a/b 表达两个分支，验收总数仍为 96。

## 前端约定

- INVALID_REQUEST：显示“请求格式或版本不受支持，请刷新页面后重试。”该错误码也表示其他格式问题，不能全部误说成版本错误。
- PLAN_MISMATCH：显示“提案信息不一致，请重新获取提案。”
- 两者都是确定性拒绝，记录 BUSINESS_REJECTED，不标记 RESPONSE_UNKNOWN，刷新恢复时不自动重发确认。重新获取提案不等于自动确认新提案。
- 本地 Mock 同步为版本/哈希格式不合法时 400，格式合法但内容不匹配时 409；确认缓存重放前同样校验。

## 已修改位置

- [接口契约](../interface-contract.md)：校验顺序、400/409 错误码。
- [测试设计](../test-design.md)：I05-a/b。
- [HTTP 请求与预期样例](../i05-http-fixtures.json)：由 HTTP 回归直接读取，避免样例与断言漂移。
- [96 条覆盖清单](P0-CASE-COVERAGE-20260922.csv)：I05 PASS。
- VoiceHttpTests：确认/取消 × 两个错误分支，真实 Spring MVC/Security 链路及 H2，断言状态码、错误码和零副作用。
- VoiceCoverageGapTests：补 service 状态码、完整提案快照与 outbox 断言。
- 前端 VoiceP0ControlPanel 与 API Mock：提示及返回口径；测试校验提示、Mock、恢复不重发。

## 验证结果

- Java 定向回归 14/14：其中新增 HTTP 4 个组合、加强 service 2 个组合，其他为现有 HTTP 回归。
- 前端 28/28：包含本轮 8 项新增验证。
- vue-tsc 与 Vite 生产构建通过。仅有原有构建体积提示。
- 此轮未重跑真实浏览器与 MySQL 专项，也未更改功能开关。

证据：[Java 日志](evidence/i05-contract-20260922/java-tests.log)、[HTTP XML](evidence/i05-contract-20260922/TEST-VoiceHttpTests.xml)、[前端测试](evidence/i05-contract-20260922/frontend-tests.log)、[构建日志](evidence/i05-contract-20260922/frontend-build.log)。

最新总清单：32 PASS、51 PARTIAL、12 NOT_VERIFIED、1 FAIL。剩余 FAIL 是 P17 缓存容量，不因 I05 完成而关闭。

可同步给同学：I05 已统一为“不支持的请求版本返回 400 INVALID_REQUEST，合法格式但错误哈希返回 409 PLAN_MISMATCH”，确认和取消均验证零副作用；前端提示、Mock 和拒绝恢复逻辑已通过回归，请以后按这一口径对接。
