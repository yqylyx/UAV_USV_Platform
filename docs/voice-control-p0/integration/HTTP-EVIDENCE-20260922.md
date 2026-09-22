# 真实 HTTP 验证与现场取证（2026-09-22）

## 本轮结果

运行基线 6cb02b3，真实 Python 062aadd 随该基线部署。入口为 http://127.0.0.1:15174，经 Vite 代理到 18081；数据库仅 uav_usv_p0_integration。

PASS：未登录 contexts 返回 401；原 p0_admin 登录；prepare 返回 v1 身份和设备帧；contexts 身份匹配；心跳实际时间持续更新；START/PAUSE/RESUME/STOP 四个 HTTP 动作均最终 SUCCEEDED/SUCCESS；PAUSE 后心跳继续；六设备名单及运行身份、commandId、stateVersion 与回执一致；STOP 后进程退出码 0。

本轮使用原算法控制接口，生成的 proposal 来源为 MANUAL。没有通过语音提案创建与用户确认来执行动作，不能将此结果记作浏览器提案闭环通过。未创建 binding/challenge，未发送 SCENE_READY 或 FRAME_APPLIED 假报告；challengeId 本轮不存在，属于未执行，不是遗漏记录。

P0 开关已恢复 false，Unity v1 开关保持 false；保留本轮数据库记录用于只读取证，不删除或清空业务数据。恢复服务会使 contexts 中的在线性发生变化，应以保存的现场报告和日志判断当时状态。

## 文件

- test-http-runner.py：本次实际运行的 HTTP 验证脚本。
- collect-readonly-evidence.sql：只读取证 SQL，含只读事务。
- evidence/http-runner-20260922.json：HTTP、proposal/execution 和数据库回执证据；不包含密码、Cookie 或 CSRF token。
- evidence/http-runner-process-20260922.txt：按 runId 提取的启动与退出日志。

## 复跑

仅在专用隔离服务临时启用 P0 后执行，禁止指向共享生产环境。脚本固定使用本机隔离端口及隔离数据库，会创建新的仿真 run 和四个控制动作；取证 SQL 本身只读。脚本不会替你打开开关。

```powershell
python docs/voice-control-p0/integration/test-http-runner.py --credentials C:/path/to/local/credentials.json --output C:/path/to/http-evidence.json --mysql D:/soteware/mysql-8.0.31-winx64/bin/mysql.exe
```

credentials.json 沿用隔离环境的 adminPassword/dbPassword 字段，仅由脚本本机读取。不要上传该文件或浏览器认证请求。脚本把数据库密码放入子进程环境，不放在命令行或报告中。失败时尝试 STOP，并保存失败报告；执行者仍须核对进程退出和恢复功能开关。持续收到非成功状态时脚本会失败，不能据 HTTP 200 宣布动作完成。

## runtimeRef → proposalId → executionId → commandId → challengeId

1. 从 prepare 或 GET /api/voice/contexts 取得 runtimeRef、runtimeGeneration 和 algorithmRunId。
2. 在 collect-readonly-evidence.sql 中替换 runtimeRef，使用本机数据库客户端运行；按运行实例筛选 proposal 和 execution。
3. 用 GET /api/voice/commands/{proposalId} 和 GET /api/voice/executions/{executionId} 保存接口快照；对照 voice_command_event 的 commandId、eventSequence、runtimeGeneration、stateVersion、affectedDeviceCodes。
4. 展示挑战标识在当前协议中叫 requestId；文档中的 challengeId 指该字段。从挑战 POST 响应和 Unity 探测/报告中采集，关联 executionId、bindingId、runtimeGeneration、sequence。数据库当前挑战在 voice_runtime_context.data_json 的 _challenge 下，不存在独立 challenge 表。
5. _challenge 会被新挑战替换，不能依靠事后 SQL 找回所有旧挑战。测试时及时保存每次挑战响应、报告响应以及脱敏网络记录，特别是 STALE 后重同步场景。
6. 后端进程日志主要用 algorithmRunId/runId 搜索，再借 contexts 映射 runtimeRef。日志未必包含所有 executionId，不能把“搜索不到日志”当成“未执行”；以数据库回执与 HTTP 证据联合判断。

建议每个场景独立目录，保存基线提交、Unity 构建版本、开始结束时间、关联 ID、HTTP 状态及响应、只读 SQL 结果、Runner/Unity 日志、PASS/FAIL/BLOCKED。保存 HAR 时去除 Cookie、Set-Cookie、Authorization、CSRF、集成令牌及登录密码。

## 仍需 Unity 配合

真实场景就绪、P0 提案 START/确认、FRAME_APPLIED、REPORTED_APPLIED、30 秒 STALE 与重新同步的完整现场闭环，仍待消息桥及新 WebGL 就绪。不得补造 challengeId 或使用模拟报告填充证据。
## 本轮关联索引

runId：1790058537904

runtimeRef：af7a834f-a1a7-40ef-a966-c11e7e765dbe

runtimeGeneration：d214a877-3f52-4a88-b1cf-1a7f65b14e6a

| 动作 | proposalId | executionId | commandId |
|---|---|---|---|
| START | c52c7b32-01b9-4101-af23-1c8ec288994f | 25b96a78-8b68-4363-8cd2-ca1c00f2a95b | 5eb9b7e1-b97a-4e33-b6e7-4e5fd0c635f6 |
| PAUSE | 39e8da85-95a5-45ca-b0f1-e1fc29163529 | 8458a65c-2d37-4413-a8a4-83aacb31b473 | 347f8a61-6e4c-4c64-9ee9-d73fddc92bdb |
| RESUME | b7f86f8c-8e72-42fe-aed6-a3992a8ef35e | 7518181d-bc3d-413a-9bdf-692e29397b5f | 9e158537-8b8f-43a0-b861-571ea48ded2e |
| STOP | 5c37eb60-6bf6-4477-abb9-bc0d9aeeb345 | f675da74-8ba8-4d05-8699-10d9f86d819a | fd812967-775e-49d3-af89-61269a9b116e |


## 场景门禁复跑与取证

将上述命令中的 test-http-runner.py 换成 test-scene-gate.py，并使用独立输出文件。此脚本在无 Unity 场景就绪的隔离环境运行：prepare 与心跳正常后，确认 START 提案返回 409 SCENE_NOT_READY，且未创建 proposal/execution；最后以真实手动 STOP 清理实例。该结果只证明门禁，不证明展示闭环。

门禁现场证据：evidence/p0-scene-gate-20260922.json。只读 SQL 实际输出：evidence/http-readonly-20260922.tsv（恢复服务后采集，须区分运行时心跳状态）。两个脚本都需要临时启用隔离 P0，执行结束后由操作者恢复开关；不要同时运行或对真实设备使用。

