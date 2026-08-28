package com.sre.poc.gateway.client;

import io.netty.channel.ChannelOption;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

import java.time.Duration;

@Component
public class ProcessorClient {

    private final WebClient webClient;
    private final String internalApiKey;

    public ProcessorClient(
            WebClient.Builder builder,
            @Value("${processor.base-url}") String baseUrl,
            @Value("${app.internal-api-key}") String internalApiKey) {
        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3000)
                .responseTimeout(Duration.ofSeconds(8));
        this.webClient = builder
                .baseUrl(baseUrl)
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
        this.internalApiKey = internalApiKey;
    }

    public String get(String path, boolean includeAuth) {
        return call(HttpMethod.GET, path, null, includeAuth, Duration.ofSeconds(8));
    }

    public String getShortTimeout(String path) {
        return call(HttpMethod.GET, path, null, true, Duration.ofSeconds(2));
    }

    public String post(String path, String body) {
        return call(HttpMethod.POST, path, body, true, Duration.ofSeconds(8));
    }

    private String call(HttpMethod method, String path, String body, boolean includeAuth, Duration timeout) {
        WebClient.RequestBodySpec spec = webClient.method(method)
                .uri(path)
                .header("X-Trace-Id", String.valueOf(MDC.get("traceId")))
                .header("X-Correlation-Id", String.valueOf(MDC.get("correlationId")));
        if (includeAuth) {
            spec.header("X-Internal-Api-Key", internalApiKey);
        }
        if (body != null) {
            spec.contentType(MediaType.APPLICATION_JSON).bodyValue(body);
        }
        return spec.retrieve().bodyToMono(String.class).block(timeout);
    }
}
