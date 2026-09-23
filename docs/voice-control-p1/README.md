# P1 D1 后端实现与测试

当前范围为本地ASR转写；[公共契约](interface-contract.md)指向D1最终稿，意图解析默认关闭。后端代码已新增，真实nly服务和ASR-only前端仍需交接。测试适配器不属于真实模型验收。

配置见application-d1-asr.yml，启动见start-d1-java.ps1（默认只检查，需先打包）；需环境变量P0_DB_PASSWORD、P0_ADMIN_PASSWORD、P0_INTEGRATION_TOKEN、P0_PYTHON、P0_RUNNER，以及D1_ASR_TOKEN和D1_ASR_MODEL_REVISION。ASR仅127.0.0.1:18082。网页统一localhost，校验现有Cookie及CSRF配置。

本轮未改数据库迁移，使用全局1000条进程内幂等，成功/失败终态30分钟、每分钟清理。发生推理超时或不确定传输故障时进入保守保护状态；mxy确认旧ASR进程退出，重启Java/ASR，所有页面刷新废弃旧请求。没有自动重启检测，不提供跨重启去重。

启用ASR时Tomcat上传读超时10秒、maxSwallowSize=0；该连接器设置会作用于该Java进程其他上传入口，D1应使用隔离服务。音频入口采用Servlet非阻塞读取且有10秒总期限，防止multipart落盘；Servlet容器不解析该路径的multipart。其他路径保持原过滤。

运行后端测试：mvn.cmd -f backend/pom.xml -Dtest=AsrServiceTests,AudioMultipartTests,LocalAsrProviderTests,AsrHttpTests,AsrEmbeddedTests,VoiceHttpTests test

契约校验：python docs/voice-control-p1/validate_contracts.py

真实服务就绪后：设置D1_TEST_USERNAME/D1_TEST_PASSWORD，再执行python docs/voice-control-p1/verify-d1-http.py --audio <本机授权音频> --mime audio/mpeg --output <本机结果JSON>。该脚本不输出Cookie、密码、原音频和完整文字；仅HTTP及同键重放冒烟，不代替浏览器D01–D12。
