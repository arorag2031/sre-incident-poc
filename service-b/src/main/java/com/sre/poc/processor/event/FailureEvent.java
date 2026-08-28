package com.sre.poc.processor.event;

public record FailureEvent(
        String timestamp,
        String serviceName,
        String traceId,
        String correlationId,
        String errorType,
        String message
) {
}
