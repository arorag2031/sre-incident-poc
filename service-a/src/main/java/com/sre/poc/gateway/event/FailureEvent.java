package com.sre.poc.gateway.event;

public record FailureEvent(
        String timestamp,
        String serviceName,
        String traceId,
        String correlationId,
        String errorType,
        String message
) {
}
