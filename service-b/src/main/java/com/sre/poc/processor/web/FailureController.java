package com.sre.poc.processor.web;

import com.sre.poc.processor.event.FailurePublisher;
import com.sre.poc.processor.repo.OrderRepository;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
import java.sql.SQLException;
import java.sql.SQLTimeoutException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.locks.ReentrantLock;

@RestController
public class FailureController {

    private static final Logger log = LoggerFactory.getLogger(FailureController.class);
    private static final ReentrantLock LOCK = new ReentrantLock();

    private final OrderRepository orders;
    private final JdbcTemplate jdbc;
    private final FailurePublisher publisher;
    private final String internalApiKey;

    public FailureController(
            OrderRepository orders,
            JdbcTemplate jdbc,
            FailurePublisher publisher,
            @Value("${app.internal-api-key}") String internalApiKey) {
        this.orders = orders;
        this.jdbc = jdbc;
        this.publisher = publisher;
        this.internalApiKey = internalApiKey;
    }

    @GetMapping("/internal/orders")
    public ResponseEntity<?> orders(HttpServletRequest request) {
        requireInternalAuth(request);
        log.info("Listing orders from PostgreSQL");
        return ResponseEntity.ok(orders.findAll());
    }

    @GetMapping("/internal/fail/null-pointer")
    public void nullPointer() {
        log.info("Core processor starting order enrichment; customer profile pointer is null");
        String profile = loadCustomerProfile(null);
        profile.toUpperCase();
    }

    @GetMapping("/internal/fail/db-timeout")
    public void dbTimeout() throws SQLTimeoutException {
        log.warn("Hikari pool wait exceeded connection-timeout=3000ms while opening a write transaction");
        throw new SQLTimeoutException(
                "HikariPool-1 - Connection is not available, request timed out after 3000ms (simulated pool exhaustion)");
    }

    @GetMapping("/internal/fail/kafka-drop")
    public void kafkaDrop() {
        log.error("Streaming producer buffer full; broker ack not received for topic orders.events");
        throw new IllegalStateException(
                "Kafka producer disconnected: network partition or broker buffer overflow on topic orders.events");
    }

    @GetMapping("/internal/fail/out-of-memory")
    public ResponseEntity<Map<String, Object>> outOfMemory() {
        log.error("JVM heap allocation failed while buffering a large order export");
        OutOfMemoryError error = new OutOfMemoryError("Java heap space (simulated) while allocating order-export buffer");
        publisher.publish(error.getClass().getSimpleName(), error.getMessage());
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(failureBody(error));
    }

    @GetMapping("/internal/fail/auth-lock")
    public ResponseEntity<Map<String, Object>> authLock(HttpServletRequest request) {
        log.warn("Service-to-service handshake rejected");
        requireInternalAuth(request);
        return ResponseEntity.ok(Map.of("status", "authenticated"));
    }

    @GetMapping("/internal/fail/deadlock")
    public void deadlock() throws SQLException {
        log.error("PostgreSQL detected deadlock between order update and inventory reservation");
        LOCK.lock();
        try {
            throw new SQLException(
                    "ERROR: deadlock detected\n  Detail: Process 84 waits for ShareLock on transaction 12; blocked by process 85.",
                    "40P01");
        } finally {
            LOCK.unlock();
        }
    }

    @PostMapping("/internal/fail/bad-payload")
    public void badPayload(@RequestBody(required = false) String body) {
        log.warn("Processor received unparseable payload: {}", body);
        throw new IllegalArgumentException("Unparseable JSON payload at $.order.items[0].qty — expected number");
    }

    @GetMapping("/internal/fail/rate-limit")
    public ResponseEntity<Map<String, Object>> rateLimit() {
        log.warn("Downstream processor rate limiter tripped for /internal/orders");
        IllegalStateException ex = new IllegalStateException("HTTP 429 Too Many Requests: processor quota exceeded (60 rpm)");
        publisher.publish("TooManyRequests", ex.getMessage());
        return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                .header("Retry-After", "30")
                .body(failureBody(ex, "TooManyRequests"));
    }

    @GetMapping("/internal/fail/disk-full")
    public void diskFull() throws IOException {
        log.error("Container overlay filesystem reports ENOSPC while rotating JSON logs");
        throw new IOException("No space left on device (simulated) writing /logs/service-b/app.json.log");
    }

    @GetMapping("/internal/hang")
    public void hang() throws InterruptedException {
        log.warn("Processor deliberately hanging to trip upstream circuit breaker");
        Thread.sleep(15_000);
    }

    @GetMapping("/internal/fail/circuit-breaker")
    public void circuitBreakerTarget() throws InterruptedException {
        hang();
    }

    @GetMapping("/internal/health-demo")
    public Map<String, Object> healthDemo() {
        Long count = jdbc.queryForObject("SELECT COUNT(*) FROM orders", Long.class);
        return Map.of("service", "service-b", "orders", count == null ? 0 : count, "traceId", String.valueOf(MDC.get("traceId")));
    }

    private void requireInternalAuth(HttpServletRequest request) {
        String header = request.getHeader("X-Internal-Api-Key");
        if (header == null || !internalApiKey.equals(header)) {
            log.error("Authentication handshake failed between gateway and processor");
            throw new SecurityException("Microservice auth lock: missing or invalid X-Internal-Api-Key");
        }
    }

    private String loadCustomerProfile(String ignored) {
        return ignored;
    }

    private Map<String, Object> failureBody(Throwable ex) {
        return failureBody(ex, ex.getClass().getSimpleName());
    }

    private Map<String, Object> failureBody(Throwable ex, String errorType) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("status", "failed");
        body.put("errorType", errorType);
        body.put("message", ex.getMessage());
        body.put("traceId", MDC.get("traceId"));
        body.put("correlationId", MDC.get("correlationId"));
        return body;
    }
}
