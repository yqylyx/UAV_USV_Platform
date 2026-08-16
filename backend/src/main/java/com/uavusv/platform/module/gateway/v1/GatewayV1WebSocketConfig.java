package com.uavusv.platform.module.gateway.v1;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class GatewayV1WebSocketConfig implements WebSocketConfigurer {

    private final GatewayV1WebSocketHandler handler;
    private final RealtimeWebSocketHandler realtimeHandler;

    public GatewayV1WebSocketConfig(
            GatewayV1WebSocketHandler handler,
            RealtimeWebSocketHandler realtimeHandler
    ) {
        this.handler = handler;
        this.realtimeHandler = realtimeHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/api/gateway/v1/mock")
                .setAllowedOriginPatterns("http://localhost:*", "http://127.0.0.1:*");
        registry.addHandler(realtimeHandler, "/api/v1/realtime")
                .setAllowedOriginPatterns("http://localhost:*", "http://127.0.0.1:*");
    }
}
