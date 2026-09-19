# P0：语音控制基础设施接口契约与测试设计

日期：2026-09-19；契约版本：`voice-p0.v1`。

**本目录包含 P0 设计基线与后续 Java 后端交付。设计文档本身不代表接口已实现或测试已通过；实施范围与实际验证见 backend-implementation.md、backend-validation.md。**

依据：桌面《UAV-USV语音大模型控制接入方案-v2.0-20260919.md》，以及平台 HEAD `4ba697a` 的本机源码。当前已有未提交文档/自动生成文件修改，本交付不覆盖这些修改。

## 文件导航

- [HTTP、权限、上下文、状态与持久化契约](interface-contract.md)
- [Java ↔ Python 进程协议](algorithm-protocol.md)
- [测试设计与 P0 实现验收门槛](test-design.md)
- [JSON Schema](contracts.schema.json)：闭合对象、字段和枚举的规范来源。
- [正反例数据](fixtures.json)：Schema 测试输入，不是真实运行记录。
- [契约自检](validate_contracts.py)：只验证数据结构、样例及文档交叉引用。

在本目录运行 `python validate_contracts.py`。要求 Python 环境提供 jsonschema；本机已有该库。本脚本不启动后端、Unity、算法进程，不连接数据库、模型供应商或 ROS。

## 本次确定的范围

- 运行域只允许 `MISSION_CENTER`，执行端只允许 `PYTHON_SIMULATION`，运行类型只允许 `STANDALONE_ALGORITHM`。
- 四个写意图：MISSION_START、MISSION_PAUSE、MISSION_RESUME、MISSION_STOP；状态通过 GET 查询。
- 主动围捕接口虽已存在，但适配器支持不一致，待基础设施通过后再扩展；P0 不接 ASR/LLM、撤退、单设备控制、ROS 或攻击执行。
- 所有写动作均须提案及按钮确认。权限使用现有 ADMIN；仅本人拥有的实例可写。OPERATOR/VIEWER 不自动获得语音写权限。
- 服务端分配 runtimeRef 和 generation；不把前端 Date.now() 编号直接当作 MissionRun 主键。
- 每个运行实例最多一个未决执行；保留本机单活动独立仿真约束。

## 与 v2.0 方案的细化

1. P0 使用结构化 `/proposals` 入口验证基础设施。P1 的 `/interpret` 将调用同一应用服务；不需要在 P0 接入或伪造模型。
2. 增加提案 INVALIDATED、执行 INVALIDATED、运行 LOST，表达上下文变更和进程丢失；这些是新模块状态，不替换现有 CommandStatus 或 MissionStatus。
3. 查询状态属于现有只读功能，不通过一个可以执行任意动作的“通用工具接口”。
4. 提案在确认前过期；确认后执行不再受原 30 秒提案窗口影响，但发送前仍校验运行代次和状态。
5. 命令生效与画面同步独立；显示结果不作为设备执行事实。
6. 未实现上述契约的旧 runner 保留原手动流程，P0 写入口返回协议不兼容，不冒充已具有命令回执。

## 状态与证据

本目录自检通过只证明 Schema、样例和引用一致。test-design.md 是原始 76 条业务用例设计；Java 后端已实现部分覆盖，具体执行证据见 [后端验证记录](backend-validation.md)，不能据此宣布跨模块用例全部通过。
## Java 后端实施补充

后端实现、展示证据补充接口、启动配置和隔离测试见 [backend-implementation.md](backend-implementation.md)。该交付不代表真实 Python/Unity 和全项目端到端已经验收。
