package com.uavusv.platform.module.runtimecontrol.controller;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RuntimeControlTraceFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(RuntimeControlTraceFilter.class);
    private static final String COMMANDS_PATH = "/api/runtime-control/commands";

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !COMMANDS_PATH.equals(request.getRequestURI());
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        long startedAt = System.currentTimeMillis();
        log.info(
                "[runtime-control-trace] inbound method={} uri={} sessionPresent={} contentType={} contentLength={}",
                request.getMethod(),
                request.getRequestURI(),
                request.getSession(false) != null,
                request.getContentType(),
                request.getContentLengthLong()
        );
        try {
            filterChain.doFilter(request, response);
        } finally {
            String principal = request.getUserPrincipal() == null
                    ? ""
                    : request.getUserPrincipal().getName();
            log.info(
                    "[runtime-control-trace] outbound method={} uri={} status={} principal={} ms={}",
                    request.getMethod(),
                    request.getRequestURI(),
                    response.getStatus(),
                    principal,
                    System.currentTimeMillis() - startedAt
            );
        }
    }
}
