package com.sre.poc.gateway.service;

import com.sre.poc.gateway.client.ProcessorClient;
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import io.github.resilience4j.timelimiter.annotation.TimeLimiter;
import org.springframework.stereotype.Service;

import java.util.concurrent.CompletableFuture;

@Service
public class CircuitProtectedProcessor {

    private final ProcessorClient processorClient;

    public CircuitProtectedProcessor(ProcessorClient processorClient) {
        this.processorClient = processorClient;
    }

    @CircuitBreaker(name = "processor", fallbackMethod = "openFallback")
    @TimeLimiter(name = "processor")
    public CompletableFuture<String> callHang() {
        return CompletableFuture.supplyAsync(() -> processorClient.getShortTimeout("/internal/hang"));
    }

    @SuppressWarnings("unused")
    private CompletableFuture<String> openFallback(Throwable ex) {
        return CompletableFuture.failedFuture(ex);
    }
}
