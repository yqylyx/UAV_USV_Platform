# P17 Runner 容量修复复测

日期：2026-09-22，时区 Asia/Shanghai（UTC+08:00）。

## 结果

- 原交接包指定脚本未修改，SHA256 为 `a240d34f0696413982fb8187d7f27660bcf2fe0745d511254cad8212172ccc5b`。
- 指定脚本真实 Python 子进程复测 PASS，退出码 0：10000 条业务拒绝被缓存，第 10001 条返回 `PROTOCOL_ERROR / CAPACITY_EXCEEDED`，旧命令原回执稳定重放。
- 新增容量测试 1 项与原协议子进程测试 7 项，共 8 项全部通过，退出码 0。完整输出见 tests-8.txt。
- 受测工作区 Runner SHA256：`b3db7e3dba77f9e219ce302ad24f5d9e598975e97e9806da3a947fd6608b21bd`，与结果 JSON 内记录一致。

## 实现及补充断言

Runner 在原有重复命令处理之后，对新命令完成格式、身份、序号检查，再检查缓存容量；容量达到 10000 时直接报告协议错误，不进入命令缓存写入、序号递增或动作执行分支。

新增 test_runner_capacity.py 使用真实 v1_main 和生产上限 10000，仅替换输入线程、sleep 与算法适配器，验证：

- 业务拒绝计入容量，溢出请求重复投递均被容量拒绝。
- 溢出之后下一序号仍被 SEQUENCE_MISMATCH 拒绝，原应接收序号未被消耗。
- 没有 ACCEPTED/SUCCEEDED，所有缓存结果保持 PREPARED / stateVersion=0。
- 第一条、第一万条缓存仍可查询；溢出命令查询 unknown。
- 原命令稳定重放，不同内容返回 COMMAND_ID_CONFLICT。
- 满容量时格式、身份、序号校验仍先于容量拒绝。
- adapter 只有初始化的 step 与 set_mission_active(False)，未执行新算法动作。

## 复现

在仓库根目录执行（输出目录须存在）：

```powershell
python docs/voice-control-p0/integration/evidence/p17-retest-20260922/package/test-runner-capacity.py --runner algorithm-service/runner.py --output runner-capacity-recheck.json
python -m unittest discover -s algorithm-service/tests -p 'test_runner*.py' -v
```

## 证据边界与后端交接

本轮不连接 Java、MySQL 或 Unity，不修改 Java，不替代后端真实 Runner 回归及 CAPACITY_EXCEEDED 通道保护测试；96 条总清单和 P0 总体验收仍由测试同学维护。I05 不在本修复范围内。

指定脚本未单独序列化溢出请求体，但接收谓词要求响应 commandId 或 relatedCommandId 等于该请求 ID；结果 JSON 保留了实际 relatedCommandId，可核对响应身份与本轮 runtimeRef/generation 一致。

本机 core.autocrlf=true；Git checkout 的换行转换可能使文件字节 SHA256 不同。回传 ZIP 附带实际受测 Runner 字节副本，以该副本及 runner-sha256.txt 核验；不要把不同换行导致的 hash 差异直接判为逻辑差异。

回传 ZIP 另附提交信息、修复 patch 与两份测试源码；仓库中的原始控制台、JSON、退出码及脚本保留可审计记录。没有附带密码、Cookie 或数据库配置。
