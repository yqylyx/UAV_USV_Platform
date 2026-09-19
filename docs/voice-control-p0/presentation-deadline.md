# E02 画面等待期限

START/RESUME 的可信 SUCCEEDED 回执被接受时，在 execution 私有快照中持久化 `_presentationStartedAt` 和 `_presentationDeadlineAt`，期限为成功接收时间后 30 秒。使用后端时钟，不使用浏览器计时，也不依赖可变 updatedAt。

读取执行（包括确认重放返回的执行）时，若算法已 SUCCEEDED、展示仍 PENDING，且 now >= deadline，则持久化为 STALE。没有请求时不需要后台定时写库；再次读取会依据原期限结算，不重新开始等待。内部字段不会进入公共响应，既有 Schema/枚举保持兼容，无需新增表或迁移。

重复成功回执不会延期。TIMED_OUT/UNKNOWN 不开始画面期限；迟到可信成功开始自己的 30 秒窗口，同时保留 timedOutAt。PAUSE/STOP 维持 NOT_REQUIRED。展示过期不改变 SUCCEEDED/SUCCESS，不发送任何算法动作。

STALE 后仍可通过现有当前绑定、一次性挑战和帧范围校验提交合法 FRAME_APPLIED，恢复 REPORTED_APPLIED；展示证据再次过期后读取仍为 STALE。挑战仍只有 5 秒有效，不因为允许迟到画面而接受过期挑战。

旧版本已成功但 PENDING、且没有持久化期限的记录，首次读取保守转 STALE，避免用 updatedAt 猜测或给历史记录重新续 30 秒。此兼容处理不改算法结果。进程重启后的旧代次仍按原 LOST 规则处理，持久化期限不代表重新接管旧进程。

前端继续分别展示算法结果与 presentationStatus；本次已可以依赖服务端 STALE，不必自行伪造展示状态。

验证使用固定时钟，覆盖 START/RESUME、成功前未知结果、成功后 29999ms/30000ms 边界、重复回执、服务对象重建后读取期限、迟到有效画面回执及再次过期、PAUSE 不创建期限。本实现随 mxy/p0-backend-20260919 分支交付；未重启项目。

## 验证记录

2026-09-19：VoiceControlTests、VoiceHttpTests、VoiceProcessTests 定向回归共 74 项通过，0 失败/错误/跳过（包含继承用例重复运行，非 74 个独立业务场景）。原 48 个契约样例、6 个 prepare 样例、黄金哈希和文档检查通过；git diff --check 通过。未运行真实 WebGL 联调或开发库迁移。
