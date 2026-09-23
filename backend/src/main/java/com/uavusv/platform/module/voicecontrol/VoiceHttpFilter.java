package com.uavusv.platform.module.voicecontrol;

import jakarta.servlet.*;
import jakarta.servlet.http.*;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.*;
import java.nio.charset.StandardCharsets;

/** Limits actual streamed bytes, including chunked requests, before MVC deserialization. */
@Component
@Order(-90)
public class VoiceHttpFilter extends OncePerRequestFilter {
    private final VoiceJson j;
    private final VoiceTime t;

    public VoiceHttpFilter(VoiceJson j, VoiceTime t) {
        this.j = j;
        this.t = t;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest req) {
        if (req.getRequestURI().substring(req.getContextPath().length()).startsWith("/api/voice/intelligence/")) return true;
        return !req.getRequestURI()
                .substring(req.getContextPath().length())
                .startsWith("/api/voice/");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest req, HttpServletResponse res, FilterChain chain)
            throws ServletException, IOException {
        res.setHeader("Cache-Control", "no-store");
        if (!"POST".equals(req.getMethod())) {
            chain.doFilter(req, res);
            return;
        }
        if (req.getContentType() == null
                || !req.getContentType()
                        .split(";", 2)[0]
                        .trim()
                        .equalsIgnoreCase("application/json")) {
            error(res, 415, "UNSUPPORTED_MEDIA_TYPE");
            return;
        }
        if (req.getHeader("Idempotency-Key") == null) {
            error(res, 400, "INVALID_REQUEST");
            return;
        }
        byte[] bytes = req.getInputStream().readNBytes(16 * 1024 + 1);
        if (bytes.length > 16 * 1024) {
            error(res, 413, "PAYLOAD_TOO_LARGE");
            return;
        }
        chain.doFilter(
                new HttpServletRequestWrapper(req) {
                    @Override
                    public ServletInputStream getInputStream() {
                        var in = new ByteArrayInputStream(bytes);
                        return new ServletInputStream() {
                            public int read() {
                                return in.read();
                            }

                            public boolean isFinished() {
                                return in.available() == 0;
                            }

                            public boolean isReady() {
                                return true;
                            }

                            public void setReadListener(ReadListener l) {
                                throw new UnsupportedOperationException("Synchronous P0 request");
                            }
                        };
                    }

                    @Override
                    public BufferedReader getReader() {
                        return new BufferedReader(
                                new InputStreamReader(getInputStream(), StandardCharsets.UTF_8));
                    }
                },
                res);
    }

    private void error(HttpServletResponse res, int status, String code) throws IOException {
        res.setStatus(status);
        res.setContentType("application/json");
        res.setCharacterEncoding("UTF-8");
        var n = j.object();
        n.put("code", code).put("message", code).putNull("data").put("timestamp", t.stamp());
        res.getWriter().write(n.toString());
    }
}
