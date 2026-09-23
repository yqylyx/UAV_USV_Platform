# P0 响应丢失与运行中刷新恢复证据

## 环境

- 后端：`http://127.0.0.1:18081`
- 前端：`http://127.0.0.1:15174`
- 数据库：`uav_usv_p0_integration`
- 时间：2026-09-22 16:46:46—16:48:17（Asia/Shanghai）
- Platform：`08fb85bba2bca358827ea8d0f507ba5b3f783c2d`
- Unity：`ab1f8a0ca946c24c85abcb4388efd27e5156f226`

## 运行身份

- algorithmRunId：`1790066814145`
- runtimeRef：`67ed0e95-7ef5-4d41-80d0-25ea6332a36d`
- runtimeGeneration：`ca5925dc-ace6-48b4-8cdd-d9aa2ba9ab45`
- 初始 bindingId：`fa8e23d9-46c6-47ee-80b5-39f848ca50db`
- RESUME executionId：`1a288fca-364e-4da7-854d-acfe1df5ce91`
- STOP executionId：`2a4897f2-2e4b-4a09-b837-6e4d24270ad2`

## 结果

- PAUSE 确认请求已由后端处理后，浏览器侧故意丢弃响应；页面出现结果未知提示，并使用原本地日志/原幂等请求恢复到 `SUCCEEDED`，未创建第二次算法动作。
- RESUME 的 `FRAME_APPLIED` 首次上报被故意阻断，execution 从 `PENDING` 进入 `STALE`，新 challenge 后恢复为 `REPORTED_APPLIED`。
- RUNNING 状态整页刷新后恢复同一 `algorithmRunId`、Unity 场景、最新帧和 execution。
- 整个运行只有一次 `POST /api/algorithm-runs/1790066814145/prepare`；刷新后只有一次 status 核对及原运行 frames 查询，没有第二次 prepare/start。
- STOP 最终为 `SUCCEEDED + NOT_REQUIRED`，停止后再次刷新仍恢复最终 execution。
- 用户切换隔离另有前端自动化测试覆盖：切换 username 后先清空 Pinia 易失状态，只读取新用户作用域的恢复记录；logout 同时清理控制日志、展示日志和该用户场景快照。

## 文件

- `browser-recovery-20260922.json`：31 个浏览器步骤、脱敏请求体/响应体、算法请求汇总。
- `readonly-export-67ed0e95.sql`：只读数据库导出。

本轮 Java 标准输出仍未重定向到文件，因此 Runner pid/exitCode 的原始日志需以后端数据库事件或下一轮启用文件日志后的记录补充。
