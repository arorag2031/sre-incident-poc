package com.sre.poc.gateway.web;

import com.sre.poc.gateway.client.ProcessorClient;
import com.sre.poc.gateway.event.FailurePublisher;
import com.sre.poc.gateway.service.CircuitProtectedProcessor;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

@RestController
public class SimulateCrashController {

    private static final Logger log = LoggerFactory.getLogger(SimulateCrashController.class);

    private final ProcessorClient processor;
    private final CircuitProtectedProcessor circuitProtectedProcessor;
    private final FailurePublisher publisher;

    public SimulateCrashController(
            ProcessorClient processor,
            CircuitProtectedProcessor circuitProtectedProcessor,
            FailurePublisher publisher) {
        this.processor = processor;
        this.circuitProtectedProcessor = circuitProtectedProcessor;
        this.publisher = publisher;
    }

    @GetMapping("/favicon.ico")
    public ResponseEntity<Void> favicon() {
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/simulate-crash/null-pointer")
    public ResponseEntity<String> nullPointer() {
        log.info("Gateway routing null-pointer simulation to Service-B");
        return proxy(() -> processor.get("/internal/fail/null-pointer", true));
    }

    @GetMapping("/simulate-crash/db-timeout")
    public ResponseEntity<String> dbTimeout() {
        log.info("Gateway routing db-timeout simulation to Service-B");
        return proxy(() -> processor.get("/internal/fail/db-timeout", true));
    }

    @GetMapping("/simulate-crash/kafka-drop")
    public ResponseEntity<String> kafkaDrop() {
        log.info("Gateway routing kafka-drop simulation to Service-B");
        return proxy(() -> processor.get("/internal/fail/kafka-drop", true));
    }

    @GetMapping("/simulate-crash/out-of-memory")
    public ResponseEntity<String> outOfMemory() {
        log.info("Gateway routing out-of-memory simulation to Service-B");
        return proxy(() -> processor.get("/internal/fail/out-of-memory", true));
    }

    @GetMapping("/simulate-crash/auth-lock")
    public ResponseEntity<String> authLock() {
        log.warn("Gateway sending processor call WITHOUT internal API key to simulate handshake failure");
        return proxy(() -> processor.get("/internal/fail/auth-lock", false));
    }

    @GetMapping("/simulate-crash/deadlock")
    public ResponseEntity<String> deadlock() {
        log.info("Gateway routing deadlock simulation to Service-B");
        return proxy(() -> processor.get("/internal/fail/deadlock", true));
    }

    @GetMapping("/simulate-crash/bad-payload")
    public ResponseEntity<Map<String, Object>> badPayload() {
        log.error("Gateway rejected corrupted JSON before it reached Service-B");
        IllegalArgumentException ex = new IllegalArgumentException(
                "API gateway payload schema corruption: unparseable JSON at $.order.items");
        publisher.publish("BadPayload", ex.getMessage());
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(body("BadPayload", ex.getMessage()));
    }

    @GetMapping("/simulate-crash/rate-limit")
    public ResponseEntity<String> rateLimit() {
        log.info("Gateway routing rate-limit simulation to Service-B");
        return proxy(() -> processor.get("/internal/fail/rate-limit", true));
    }

    @GetMapping("/simulate-crash/disk-full")
    public ResponseEntity<String> diskFull() {
        log.info("Gateway routing disk-full simulation to Service-B");
        return proxy(() -> processor.get("/internal/fail/disk-full", true));
    }

    @GetMapping("/simulate-crash/circuit-breaker")
    public ResponseEntity<Map<String, Object>> circuitBreaker() {
        log.warn("Gateway invoking Service-B hang endpoint behind Resilience4j circuit breaker");
        Throwable last = null;
        for (int i = 0; i < 3; i++) {
            try {
                circuitProtectedProcessor.callHang().join();
            } catch (CompletionException | CallNotPermittedException ex) {
                last = unwrap(ex);
                log.error("Circuit/time limiter iteration {} failed: {}", i + 1, last.toString());
            }
        }
        String message = last == null
                ? "Resilience4j circuit breaker OPEN after cascaded Service-B timeouts"
                : "Resilience4j circuit breaker tripped: " + last.getClass().getSimpleName() + " — " + safeMsg(last);
        publisher.publish("CircuitBreakerOpen", message);
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(body("CircuitBreakerOpen", message));
    }

    private ResponseEntity<String> proxy(Call call) {
        try {
            String body = call.get();
            return ResponseEntity.ok(body);
        } catch (WebClientResponseException ex) {
            return ResponseEntity.status(ex.getStatusCode()).body(ex.getResponseBodyAsString());
        }
    }

    private Map<String, Object> body(String errorType, String message) {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("status", "failed");
        map.put("errorType", errorType);
        map.put("message", message);
        map.put("traceId", MDC.get("traceId"));
        map.put("correlationId", MDC.get("correlationId"));
        return map;
    }

    private static Throwable unwrap(Throwable ex) {
        Throwable current = ex;
        while (current.getCause() != null && current != current.getCause()) {
            if (current instanceof CompletionException || current instanceof ExecutionException) {
                current = current.getCause();
                continue;
            }
            break;
        }
        return current;
    }

    private static String safeMsg(Throwable ex) {
        return ex.getMessage() == null ? ex.getClass().getSimpleName() : ex.getMessage();
    }

    @FunctionalInterface
    private interface Call {
        String get();
    }
}
