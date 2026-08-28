package com.sre.poc.gateway.event;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Instant;

@Component
public class FailurePublisher {

    private static final Logger log = LoggerFactory.getLogger(FailurePublisher.class);

    private final StringRedisTemplate redis;
    private final ObjectMapper mapper;
    private final String channel;
    private final String serviceName;

    public FailurePublisher(
            StringRedisTemplate redis,
            ObjectMapper mapper,
            @Value("${app.failure-channel}") String channel,
            @Value("${app.service-name}") String serviceName) {
        this.redis = redis;
        this.mapper = mapper;
        this.channel = channel;
        this.serviceName = serviceName;
    }

    public void publish(String errorType, String message) {
        FailureEvent event = new FailureEvent(
                Instant.now().toString(),
                serviceName,
                valueOrUnknown(MDC.get("traceId")),
                valueOrUnknown(MDC.get("correlationId")),
                errorType,
                message
        );
        try {
            String payload = mapper.writeValueAsString(event);
            redis.convertAndSend(channel, payload);
            log.error("Published failure event to {}: {}", channel, payload);
        } catch (Exception e) {
            log.error("Unable to publish failure event", e);
        }
    }

    private static String valueOrUnknown(String value) {
        return value == null || value.isBlank() ? "unknown" : value;
    }
}
