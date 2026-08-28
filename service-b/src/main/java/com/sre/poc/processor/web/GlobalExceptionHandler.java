package com.sre.poc.processor.web;

import com.sre.poc.processor.event.FailurePublisher;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.resource.NoResourceFoundException;

import java.util.LinkedHashMap;
import java.util.Map;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);
    private final FailurePublisher publisher;

    public GlobalExceptionHandler(FailurePublisher publisher) {
        this.publisher = publisher;
    }

    @ExceptionHandler(NoResourceFoundException.class)
    public ResponseEntity<Void> missingStatic(NoResourceFoundException ex) {
        log.debug("Ignoring missing static resource: {}", ex.getResourcePath());
        return ResponseEntity.notFound().build();
    }

    @ExceptionHandler(Throwable.class)
    public ResponseEntity<Map<String, Object>> handle(Throwable ex) {
        String errorType = ex.getClass().getSimpleName();
        String message = ex.getMessage() == null ? errorType : ex.getMessage();
        log.error("Unhandled failure type={} msg={}", errorType, message, ex);
        if (!isBrowserNoise(errorType, message)) {
            publisher.publish(errorType, truncate(message));
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("status", "failed");
        body.put("errorType", errorType);
        body.put("message", message);
        body.put("traceId", MDC.get("traceId"));
        body.put("correlationId", MDC.get("correlationId"));
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(body);
    }

    private static String truncate(String message) {
        return message.length() <= 240 ? message : message.substring(0, 240);
    }

    private static boolean isBrowserNoise(String errorType, String message) {
        String haystack = (errorType + " " + message).toLowerCase();
        return haystack.contains("favicon")
                || haystack.contains("no static resource")
                || haystack.contains("noresourcefound")
                || haystack.contains("actuator/health");
    }
}
