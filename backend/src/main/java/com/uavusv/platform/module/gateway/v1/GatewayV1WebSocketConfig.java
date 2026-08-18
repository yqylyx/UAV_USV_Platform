package com.uavusv.platform.module.gateway.v1;

import com.uavusv.platform.module.visualsensor.integration.VisualSensorFrameStreamHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class GatewayV1WebSocketConfig implements WebSocketConfigurer {

    private final GatewayV1WebSocketHandler handler;
    private final RealtimeWebSocketHandler realtimeHandler;
    private final VisualSensorFrameStreamHandler visualSensorFrameStreamHandler;

    public GatewayV1WebSocketConfig(
            GatewayV1WebSocketHandler handler,
            RealtimeWebSocketHandler realtimeHandler,
            VisualSensorFrameStreamHandler visualSensorFrameStreamHandler
    ) {
        this.handler = handler;
        this.realtimeHandler = realtimeHandler;
        this.visualSensorFrameStreamHandler = visualSensorFrameStreamHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/api/gateway/v1/mock")
                .setAllowedOriginPatterns("http://localhost:*", "http://127.0.0.1:*");
        registry.addHandler(realtimeHandler, "/api/v1/realtime")
                .setAllowedOriginPatterns("http://localhost:*", "http://127.0.0.1:*");
        registry.addHandler(visualSensorFrameStreamHandler, "/api/visual-sensors/stream")
                .setAllowedOriginPatterns("http://localhost:*", "http://127.0.0.1:*");
    }
}
