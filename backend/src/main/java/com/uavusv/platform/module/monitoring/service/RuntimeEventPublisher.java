package com.uavusv.platform.module.monitoring.service;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.time.LocalDateTime;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

@Service
public class RuntimeEventPublisher {

    private final List<SseEmitter> emitters = new CopyOnWriteArrayList<>();

    public SseEmitter subscribe() {
        SseEmitter emitter = new SseEmitter(0L);
        emitters.add(emitter);
        emitter.onCompletion(() -> emitters.remove(emitter));
        emitter.onTimeout(() -> emitters.remove(emitter));
        emitter.onError(error -> emitters.remove(emitter));
        send(emitter, "connected", LocalDateTime.now().toString());
        return emitter;
    }

    public void publishRuntimeChange() {
        for (SseEmitter emitter : emitters) {
            send(emitter, "runtime-change", LocalDateTime.now().toString());
        }
    }

    @Scheduled(fixedDelay = 15000)
    public void keepAlive() {
        for (SseEmitter emitter : emitters) {
            send(emitter, "keepalive", LocalDateTime.now().toString());
        }
    }

    private void send(SseEmitter emitter, String eventName, String data) {
        try {
            emitter.send(SseEmitter.event().name(eventName).data(data));
        } catch (IOException | RuntimeException exception) {
            emitters.remove(emitter);
            completeQuietly(emitter);
        }
    }

    private void completeQuietly(SseEmitter emitter) {
        try {
            emitter.complete();
        } catch (RuntimeException ignored) {
            // The browser may already have closed the SSE response.
        }
    }
}
