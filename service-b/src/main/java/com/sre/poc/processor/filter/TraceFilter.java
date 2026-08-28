package com.sre.poc.processor.filter;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Optional;
import java.util.UUID;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceFilter extends OncePerRequestFilter {

    @Value("${app.service-name}")
    private String serviceName;

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        String traceId = Optional.ofNullable(request.getHeader("X-Trace-Id")).filter(s -> !s.isBlank())
                .orElse(UUID.randomUUID().toString());
        String correlationId = Optional.ofNullable(request.getHeader("X-Correlation-Id")).filter(s -> !s.isBlank())
                .orElse(UUID.randomUUID().toString());
        MDC.put("traceId", traceId);
        MDC.put("correlationId", correlationId);
        MDC.put("serviceName", serviceName);
        response.setHeader("X-Trace-Id", traceId);
        response.setHeader("X-Correlation-Id", correlationId);
        try {
            filterChain.doFilter(request, response);
        } finally {
            MDC.clear();
        }
    }
}
