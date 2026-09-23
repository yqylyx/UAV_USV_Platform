package com.uavusv.platform.module.voiceintelligence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.uavusv.platform.module.voicecontrol.VoiceFailure;

import jakarta.servlet.*;
import jakarta.servlet.http.*;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

/** Servlet nonblocking upload: a total deadline, not a reset-on-each-byte socket timeout. */
@Component
@Order(-91)
public class AsrUploadFilter extends OncePerRequestFilter {
    public static final String BODY = "asr.body", DEADLINE = "asr.deadline";
    private final AsrService service;
    private final ObjectMapper json;
    private final Semaphore uploads = new Semaphore(2);

    public AsrUploadFilter(AsrService service, ObjectMapper json) {
        this.service = service;
        this.json = json;
    }

    protected boolean shouldNotFilter(HttpServletRequest r) {
        return !r.getMethod().equals("POST")
                || !r.getRequestURI()
                        .substring(r.getContextPath().length())
                        .equals(AsrIngressFilter.PATH);
    }

    protected void doFilterInternal(
            HttpServletRequest req, HttpServletResponse res, FilterChain chain)
            throws IOException, ServletException {
        try {
            service.authorize();
            if (req.getContentLengthLong() > AudioMultipart.MAX_BODY)
                throw new AsrFailure(413, "VOICE_AUDIO_TOO_LARGE");
        } catch (VoiceFailure e) {
            write(res, new AsrFailure(e.status, e.code));
            return;
        } catch (AsrFailure e) {
            write(res, e);
            return;
        }
        if (!uploads.tryAcquire()) {
            write(res, new AsrFailure(429, "VOICE_RATE_LIMITED", 2, false));
            return;
        }
        AsyncContext async;
        try {
            async = req.startAsync(req, res);
        } catch (RuntimeException e) {
            uploads.release();
            throw e;
        }
        async.setTimeout(10000);
        AtomicBoolean done = new AtomicBoolean(), released = new AtomicBoolean();
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        Runnable release =
                () -> {
                    if (released.compareAndSet(false, true)) uploads.release();
                };
        java.util.function.Consumer<AsrFailure> fail =
                e -> {
                    if (done.compareAndSet(false, true)) {
                        try {
                            write(res, e);
                        } catch (IOException ignored) {
                        } finally {
                            release.run();
                            async.complete();
                        }
                    }
                };
        async.addListener(
                new AsyncListener() {
                    public void onTimeout(AsyncEvent e) {
                        fail.accept(new AsrFailure(408, "VOICE_UPLOAD_TIMEOUT"));
                    }

                    public void onError(AsyncEvent e) {
                        fail.accept(AsrFailure.invalid());
                    }

                    public void onComplete(AsyncEvent e) {
                        release.run();
                    }

                    public void onStartAsync(AsyncEvent e) {}
                });
        ServletInputStream input = req.getInputStream();
        input.setReadListener(
                new ReadListener() {
                    public void onDataAvailable() throws IOException {
                        byte[] block = new byte[8192];
                        while (!done.get() && input.isReady() && !input.isFinished()) {
                            int n = input.read(block);
                            if (n < 0) break;
                            if (bytes.size() + n > AudioMultipart.MAX_BODY) {
                                fail.accept(new AsrFailure(413, "VOICE_AUDIO_TOO_LARGE"));
                                return;
                            }
                            bytes.write(block, 0, n);
                        }
                    }

                    public void onAllDataRead() {
                        if (done.compareAndSet(false, true)) {
                            req.setAttribute(BODY, bytes.toByteArray());
                            req.setAttribute(
                                    DEADLINE, System.nanoTime() + TimeUnit.SECONDS.toNanos(120));
                            release.run();
                            async.dispatch();
                        }
                    }

                    public void onError(Throwable t) {
                        fail.accept(AsrFailure.invalid());
                    }
                });
    }

    private void write(HttpServletResponse res, AsrFailure e) throws IOException {
        res.setStatus(e.status);
        res.setContentType("application/json");
        res.setCharacterEncoding("UTF-8");
        res.setHeader("Cache-Control", "no-store");
        if (e.retryAfter != null) res.setHeader("Retry-After", e.retryAfter.toString());
        json.writeValue(res.getOutputStream(), AsrResponses.error(e).body());
    }
}
