# P1 当前接口实施入口：D1本地ASR

当前规范：[规划v1.3](P1-ASR-规划调整与接口契约测试设计-v1.3.md)；分工：[v1.1](P1-ASR-阶段详细分工与联调交接-v1.1.md)。已由用户提供D1最终确认稿。

POST /api/voice/intelligence/transcriptions 是当前D1入口；POST /api/voice/intelligence/interpretations 保留但关闭，不执行模型解析或创建提案。

机器Schema的转写格式已收窄到D1 WebM/Opus与MP3，新增内部成功/错误结构和VOICE_TRANSCRIPT_TOO_LONG。历史意图定义保留，仅供E1/后续阶段，不代表D1启用。原v1.1见 [历史契约](interface-contract-v1.1-history.md)，其20秒、五格式、长期幂等条款不用于D1。

当前实现配置名为app.voiceintelligence.enabled/base-url/token/model-revision/model-alias；默认关闭。内存幂等1000条、终态30分钟、每分钟清理。模型超时/不确定传输错误导致本Java实例进入保护状态，只允许已有键重放，新请求429；mxy人工确认旧ASR进程退出并协调重启Java/ASR和页面。仅ready=200不解除此保护。

新增内部结构的Schema验证不能证明Java—Python真实服务已联调，关联ID一致、协议状态映射和模型revision由Java运行时另行校验。
