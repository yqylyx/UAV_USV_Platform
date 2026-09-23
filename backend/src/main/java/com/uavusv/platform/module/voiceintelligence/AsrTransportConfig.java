package com.uavusv.platform.module.voiceintelligence;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.*;

@Configuration
@ConditionalOnProperty(name = "app.voiceintelligence.enabled", havingValue = "true")
public class AsrTransportConfig {
    @Bean
    WebServerFactoryCustomizer<TomcatServletWebServerFactory> asrUploadTimeout() {
        return factory ->
                factory.addConnectorCustomizers(
                        connector -> {
                            connector.setProperty("disableUploadTimeout", "false");
                            connector.setProperty("connectionUploadTimeout", "10000");
                            connector.setProperty("maxSwallowSize", "0");
                        });
    }
}
