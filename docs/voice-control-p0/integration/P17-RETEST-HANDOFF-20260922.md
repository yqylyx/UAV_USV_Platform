# P17 指定脚本复测交接包

本包的 test-runner-capacity.py 与后端原证据包中的脚本逐字节一致，没有修改通过条件。脚本 SHA256：

`a240d34f0696413982fb8187d7f27660bcf2fe0745d511254cad8212172ccc5b`

请在 Python 同学已修复的 Platform 仓库内，使用能够运行该 Runner 的 Python 环境执行。这里测试的是新的独立子进程，不连接 Java、MySQL 或 Unity，不需要提供数据库密码。

## 复测步骤（PowerShell）

把本包解压至任意位置，先进入已修复仓库根目录，再将下面的脚本路径替换为实际解压路径。若 python 不是算法依赖所在环境，请换成那个环境的 python.exe 完整路径。

```powershell
$evidenceDir = Join-Path (Get-Location) ('p17-evidence-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $evidenceDir | Out-Null
$runnerPath = (Resolve-Path './algorithm-service/runner.py').Path
Get-FileHash -LiteralPath $runnerPath -Algorithm SHA256 | Format-List | Out-File "$evidenceDir/runner-sha256.txt"
python 'C:/path/to/P17-retest/test-runner-capacity.py' --runner $runnerPath --output "$evidenceDir/runner-capacity.json" 2>&1 | Tee-Object "$evidenceDir/console.txt"
$testExitCode = $LASTEXITCODE
"exitCode=$testExitCode" | Set-Content "$evidenceDir/exit-code.txt"
```

脚本逐条投递 10000 条业务拒绝命令，因此需要等待；每 2000 条输出一次进度。不要用缩小容量或改脚本通过条件替代这轮指定脚本复测。输出目录必须先建立。

## 预期与证据边界

- 正常结束时控制台出现 P17 PASS CAPACITY_EXCEEDED，退出码 0。
- runner-capacity.json：result=PASS、cachedCommands=10000、overflow.errorCode=CAPACITY_EXCEEDED、oldReplayStable=true。
- 同时人工核对 overflow.kind=PROTOCOL_ERROR、relatedCommandId 对应溢出命令，运行身份与本轮一致。
- 此原脚本直接覆盖“10000 条被缓存的业务拒绝、满容量拒绝新命令、旧命令原回执稳定重放”。它不直接完整证明“状态/序号不推进、无缓存增删、旧命令查询与内容冲突、apply 调用次数”，这些仍需提供同学新增容量测试和既有 7 项协议测试的具体断言与输出。不能把原脚本 PASS 扩大成所有边界已验收。

## 请回传

1. runner-capacity.json、console.txt、exit-code.txt、runner-sha256.txt。
2. 新增容量测试及原 7 项协议测试的代码与完整测试输出。
3. 修复所在分支、commit 和涉及文件；若尚未提交，请明确有未提交修改，Runner 的 SHA256 必须与复测对象一致。
4. 请把修复推送到自己的 Python 分支并提供远端 commit，或提供可应用的代码补丁；只有文字说明与 PASS 截图，后端无法复现同一版本。

不需要发送数据库配置、密码、Cookie 或整个本机环境。

## 后端接续操作（由后端同学执行）

收到可取得的修复代码后，先核对 diff 和 SHA256，再用相同 Runner 重跑指定脚本。随后调用后端已有 test-real-runner.ps1，通过 -Runner 指向该文件，核验 Java 真实启动参数、Ready、心跳、设备列表、四动作及正常 STOP 退出。

再执行 VoiceRealRunnerFaultTests 的故障场景：崩溃、心跳丢失、查询恢复、旧代次消息、STOP ACK 前 EOF、STOP 最终回执丢失。故障类依赖本地最新测试代理与后端测试基线；Python 同学不需要复制修改 Java 代码。测试使用独立 H2 和子进程，不需要启动隔离 Web 服务。

注意：现有 Java 故障测试并不直接验证收到 CAPACITY_EXCEEDED 时的行为，需补一个针对该 PROTOCOL_ERROR 的关联/通道保护检查，确认不被当作成功且不自动重发。

最后把 P17 的脚本结果、Runner commit/hash、Java 回归结果关联到覆盖清单。当前后端本机 Runner 仍是旧版本，SHA256 为 C5A202692006B38506817C9C56B8F897BD99A74EF75F384147CB6DE119CA597B；因此现在保留 P17 FAIL，备注“同学本地已修，指定脚本与后端复验待完成”，不能先改 PASS。
