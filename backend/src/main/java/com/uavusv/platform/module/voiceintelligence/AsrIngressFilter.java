package com.uavusv.platform.module.voiceintelligence;

import jakarta.servlet.*;
import jakarta.servlet.http.*;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.*;
import java.util.*;

/**
 * Hide multipart from servlet parsing, including CSRF parameter fallback. Body stays untouched
 * until authorization.
 */
@Component
@Order(-110)
public class AsrIngressFilter extends OncePerRequestFilter {
    public static final String PATH = "/api/voice/intelligence/transcriptions",
            TYPE = "asr.originalContentType";

    protected boolean shouldNotFilter(HttpServletRequest r) {
        return !r.getRequestURI().substring(r.getContextPath().length()).equals(PATH);
    }

    protected void doFilterInternal(HttpServletRequest r, HttpServletResponse s, FilterChain chain)
            throws IOException, ServletException {
        s.setHeader("Cache-Control", "no-store");
        String id = r.getHeader("X-Request-ID");
        if (id != null && AudioMultipart.UUID.matcher(id).matches())
            s.setHeader("X-Request-ID", id);
        r.setAttribute(TYPE, r.getContentType());
        chain.doFilter(
                new HttpServletRequestWrapper(r) {
                    public String getContentType() {
                        return "application/octet-stream";
                    }

                    public String getParameter(String n) {
                        return null;
                    }

                    public Map<String, String[]> getParameterMap() {
                        return Map.of();
                    }

                    public Enumeration<String> getParameterNames() {
                        return Collections.emptyEnumeration();
                    }

                    public String[] getParameterValues(String n) {
                        return null;
                    }

                    public Collection<Part> getParts() throws ServletException {
                        throw new ServletException("ASR multipart is memory only");
                    }

                    public Part getPart(String n) throws ServletException {
                        throw new ServletException("ASR multipart is memory only");
                    }
                },
                s);
    }
}
