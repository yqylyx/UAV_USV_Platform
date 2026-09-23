# nly P1-ASR D1 实现与交接（2026-09-23）

更新：提交交接以 [最新契约对齐](nly-d1-contract-alignment-20260923.md) 为准。已读取mxy远端425a96c：非法内部参数现为503 ASR_UNAVAILABLE；Java已提供Content-Length。下文“尚未推送”和旧远端基线是首轮开发时点记录，不代表发布后的状态。Java重启防旧键重复推理为明确待修项，不能据此文档宣称已保障。

## 文档评审结论

已完整核对用户提供的《P1-ASR-规划调整与接口契约测试设计-v1.3(1).md》和《P1-ASR-阶段详细分工与联调交接-v1.1(1).md》。职责、mxy同机部署、D1/E1分层及纯语音转文字范围一致，可以实施。未修改原附件或mxy负责的公共机器契约/后端实现。

两个需要mxy确认的实现细节（不新增公共接口）：

1. 非法内部参数：原HTTP400建议已撤回，现为HTTP503、固定结构 `ASR_UNAVAILABLE`，与425a96c映射一致；未知错误仍按约定返回502。
2. Java到Python必须提供Content-Length，内部服务不接受chunked multipart；最多6MiB，Java可内存构造。忙时Retry-After:2为重试建议，不承诺2秒内完成，不允许适配器自动重试。

## 基线和改动边界

- 当前分支：`nly/voice-control-p1-preparation`，起点 `f603b01035316cc18d91c332fd578658c7b093ea`。
- 已成功fetch远端；开发时该远端分支仍为f603b01，mxy/p1-backend-20260923为09863cd。
- 新增 `asr-service/`、前端ASR-only组件、独立 `/asr` 路由、导航及配置说明；既有转写API增加D1超时入口。
- ASR-only开关默认false。未修改用户本机.env.local，未替mxy启用后端，未更改数据库。
- 未修改backend、algorithm-service/runner.py或Unity C#。
- Unity VirtualFleet只读核对HEAD：`ab1f8a0ca946c24c85abcb4388efd27e5156f226`，工作树无修改；不是本轮真实画面验收结果。
- 原两个未跟踪文件（供应商选型文档、export-runtime-evidence.ps1）保留，不属于本次交付。

## nly已实现

### 前端

- `/asr` 不需要仿真实例，初次访问不启动系统总览Unity；从仿真页切入保留已加载的P0会话。
- 新增 `VITE_VOICE_ASR_ONLY=false`；启用后展示独立入口及语音栏ASR组件，隐藏旧意图解析组件。
- ASR-only只请求Java转写接口，无Mock自动降级；后端test-fixture标明不计入验收。
- 录音WebM/Opus，58秒单调计时软停止并等待尾帧；另有MP3文件测试入口。
- 真实CSRF及三标识沿用既有适配器；ASR等待140秒（组件计时包含CSRF准备）；无自动POST重试。
- 完整文字展示和编辑，不按200字裁剪；显示模型和时长，无候选/提案事件。
- 10分钟手动原键/Blob恢复，重试不续期；遵守Retry-After。取消仅停止等待；卸载、权限或用户变化清理、隔离迟到结果。

### Python

- 两个内部接口、loopback监听、内部凭据、启动预热与ready、busy单槽覆盖读请求/解码/推理。
- 固定small模型四文件SHA256，CPU INT8默认4线程；无运行时下载和云端回退。
- 内存multipart、5MiB文件/6MiB请求、真实WebM/Opus与MP3、单音频轨、声道/采样率校验、16kHz单声道采样点上限。
- 静音/超长/损坏/鉴权/超时等固定错误。推理超时槽位不提前释放。
- 原生推理不做强制线程取消；D1卡死按文档人工重启独立PID，不影响算法Runner。
- 依赖锁定、模型指纹、启动/关闭及真实HTTP冒烟步骤见 `asr-service/README.md`。

## 已执行验证（nly i7开发机，不是mxy验收）

| 层级 | 结果 | 边界 |
|---|---|---|
| 前端Vitest | 11文件、83项全部通过 | 19项新增，含录音尾帧、58秒、恢复/冷却/10分钟、140秒、账号隔离、D1 API等；模拟浏览器测试不是真人麦克风验收 |
| 类型检查/构建 | vue-tsc + Vite通过 | 仍有已有vueuse注解和包体积警告 |
| Python unittest | 18项通过 | 含真实编码/解码，HTTP边界使用明确FakeEngine；不冒充真实识别 |
| 真实Python HTTP | MP3/WebM成功，静音422，损坏MP3受控415 | 真实small模型，4线程，Hub离线模式；不是Java/浏览器或网络物理断开验收 |

真实HTTP首轮记录：

| 样本 | 状态 | HTTP耗时 | requestId |
|---|---|---|---|
| 原始授权MP3（带坏尾包） | 415 ASR_AUDIO_FORMAT_UNSUPPORTED | 0.045s | 5294b74d-c97e-4a44-bde4-9d5242e30412 |
| 显式在内存重编码MP3 | 200，durationMs=5784 | 2.174s | 2c4334d3-593a-4f23-b734-64132e6ad14d |
| 同内容转码WebM/Opus | 200，durationMs=5784 | 1.833s | a4e166f0-9081-4c57-bc7c-daad7163b46e |
| 2秒合成静音 | 422 ASR_NO_SPEECH | 0.034s | d1502bbe-6643-4814-91ab-5470d8ca78e0 |

原始文件SHA256：`08859b511bc43a0e9572b75bece5602f77aaf29c38c6bf4ab5161443cdaf19c0`。原文件未修改。坏包位于字节231360，953字节；旧独立脚本的宽松解码跳过坏包，新服务严格拒绝。因此不得宣传“原始损坏MP3直接成功”。显式重编码仅是诊断与正常容器测试；服务没有偷偷修补请求。

原始识别全文及私有结果JSON保留在本机 `F:/Tool/asr-cpu-test/d1-http-smoke.json`，不默认入Git。真实测试只启动自己创建的ASR子进程并确认退出；没有关停已有前后端或算法。

## mxy接下来做什么

1. 确认两个内部细节，并同步公共契约、Schema与样例（nly未代改共享契约）。
2. 在i5部署机安装锁定环境，部署同revision模型文件；设置Java和Python共用凭据，不在聊天/日志发值。
3. Java实现/核验120秒总期限、动态剩余期限、ID及模型校验、错误映射、权限/CSRF、内存幂等或已有持久化方案。
4. 确认Java multipart和任何代理均无音频临时落盘；Python只验证了自身内存路径，不能代替全链路隐私验收。
5. 前端设置VITE_VOICE_ASR_ONLY=true并重启/重新构建；通过统一localhost会话登录后访问/asr，不先生成仿真。
6. D01–D12按真实环境执行，尤其真人录音、浏览器版本/麦克风权限、原始录音格式、重启、缓存、权限、P0兼容。
7. 交给nly复核D01/D07/D12及人工重启证据；双方通过后只宣布D1，不标E1完成。

## 尚未完成，不能提前宣称通过

- mxy部署机安装、性能、线程与Unity并行资源评估。
- Java真实HTTP集成、完整内存幂等及权限测试（mxy职责）。
- 浏览器真人麦克风、网络断开情况下的整链路、实际Cookie/CSRF、30分钟清理。
- D07数据库无新增控制记录、D12真实手工四动作和Unity画面兼容复核。
- E1的全部长期持久化、跨重启、故障恢复、五格式、60条质量统计。

截至此交接文件生成：实现与开发测试已完成，正式D1联调/验收待mxy接入；本轮未推送远端。
