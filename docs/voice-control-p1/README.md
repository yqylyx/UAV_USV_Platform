# P1 D1 后端实现与测试

当前范围为本地ASR转写；[公共契约](interface-contract.md)指向D1最终稿，意图解析默认关闭。nly的f630a74已合入mxy联调分支；真实Java—Python HTTP、结果重放和Java重启防重已在mxy机通过，真实浏览器麦克风验收仍待执行。测试适配器不属于真实模型验收。

配置见application-d1-asr.yml，启动见start-d1-java.ps1（默认只检查，需先打包）；需环境变量P0_DB_PASSWORD、P0_ADMIN_PASSWORD、P0_INTEGRATION_TOKEN、P0_PYTHON、P0_RUNNER，以及D1_ASR_TOKEN和D1_ASR_MODEL_REVISION。ASR仅127.0.0.1:18082。网页统一localhost，校验现有Cookie及CSRF配置。

V20新增最小受理墓碑，只保存userId、endpoint、requestId、音频指纹和受理/过期时间，不保存音频或文字。内存结果仍按全局1000条、终态30分钟和每分钟清理；墓碑保留7天。Java重启后同键同内容返回409 VOICE_REQUEST_OUTCOME_UNKNOWN，同键不同内容返回409 IDEMPOTENCY_CONFLICT，均禁止再次调用Python；7天到期后才允许作为新请求受理。

启用ASR时Tomcat上传读超时10秒、maxSwallowSize=0；该连接器设置会作用于该Java进程其他上传入口，D1应使用隔离服务。音频入口采用Servlet非阻塞读取且有10秒总期限，防止multipart落盘；Servlet容器不解析该路径的multipart。其他路径保持原过滤。

运行后端测试：mvn.cmd -f backend/pom.xml -Dtest=AsrAcceptanceStoreTests,AsrServiceTests,AudioMultipartTests,LocalAsrProviderTests,AsrHttpTests,AsrEmbeddedTests,VoiceHttpTests test

真实MySQL迁移专项：配置仅指向服务器根地址的VOICE_TEST_MYSQL_URL以及测试账号后，运行mvn.cmd -f backend/pom.xml -Dtest=AsrMysqlMigrationTests test。测试只创建并删除自己随机命名的uav_usv_asr_test_<32位十六进制>数据库。

契约校验：python docs/voice-control-p1/validate_contracts.py

真实服务就绪后：设置D1_TEST_USERNAME/D1_TEST_PASSWORD，再执行python docs/voice-control-p1/verify-d1-http.py --audio <本机授权音频> --mime audio/mpeg --output <本机结果JSON>。Java重启后可增加--request-id <原UUID> --expect-code VOICE_REQUEST_OUTCOME_UNKNOWN验证墓碑。脚本不输出Cookie、密码、原音频和完整文字；仅HTTP及同键重放/重启保护冒烟，不代替浏览器D01–D12。
