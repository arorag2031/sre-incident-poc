package com.sre.poc.gateway.web;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 1)
public class MaintenanceFilter extends OncePerRequestFilter {

    private static final String MAINTENANCE_HTML = """
            <!DOCTYPE html>
            <html lang="en">
            <head>
              <meta charset="UTF-8"/>
              <meta name="viewport" content="width=device-width, initial-scale=1"/>
              <title>Under Maintenance</title>
              <style>
                :root { color-scheme: dark; }
                body { margin: 0; min-height: 100vh; display: grid; place-items: center;
                       font-family: ui-sans-serif, system-ui, sans-serif; background: #0b1220; color: #e8eefc; }
                .card { max-width: 520px; padding: 36px 32px; border: 1px solid #243656; border-radius: 16px;
                        background: #111a2e; text-align: center; }
                h1 { margin: 0 0 12px; }
                p { color: #9db0d0; line-height: 1.5; }
                code { background: #152238; padding: 2px 6px; border-radius: 4px; }
              </style>
            </head>
            <body>
              <main class="card">
                <h1>Under Maintenance</h1>
                <p>The SRE Incident Copilot and crash console are temporarily offline.
                   Log events are not processed while <code>ALLOW_Display=False</code>.</p>
              </main>
            </body>
            </html>
            """;

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        return path.startsWith("/actuator");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        if (displayAllowed()) {
            filterChain.doFilter(request, response);
            return;
        }
        response.setStatus(HttpServletResponse.SC_SERVICE_UNAVAILABLE);
        response.setContentType(MediaType.TEXT_HTML_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getWriter().write(MAINTENANCE_HTML);
    }

    static boolean displayAllowed() {
        String file = System.getenv().getOrDefault("DISPLAY_FLAG_FILE", "/config/.env");
        Path path = Path.of(file);
        if (Files.isRegularFile(path)) {
            try {
                for (String line : Files.readAllLines(path, StandardCharsets.UTF_8)) {
                    String stripped = line.trim();
                    if (stripped.isEmpty() || stripped.startsWith("#")) {
                        continue;
                    }
                    if (stripped.startsWith("export ")) {
                        stripped = stripped.substring(7).trim();
                    }
                    int eq = stripped.indexOf('=');
                    if (eq <= 0) {
                        continue;
                    }
                    String key = stripped.substring(0, eq).trim();
                    if ("ALLOW_Display".equals(key) || "ALLOW_DISPLAY".equals(key)) {
                        return parseBool(stripped.substring(eq + 1), true);
                    }
                }
            } catch (IOException ignored) {
                // fall through to env var
            }
        }
        return parseBool(System.getenv().getOrDefault("ALLOW_Display",
                System.getenv().getOrDefault("ALLOW_DISPLAY", "True")), true);
    }

    private static boolean parseBool(String raw, boolean defaultValue) {
        if (raw == null) {
            return defaultValue;
        }
        String value = raw.trim().replace("\"", "").replace("'", "").toLowerCase(Locale.ROOT);
        if (value.isEmpty()) {
            return defaultValue;
        }
        if (value.equals("true") || value.equals("1") || value.equals("yes") || value.equals("on")) {
            return true;
        }
        if (value.equals("false") || value.equals("0") || value.equals("no") || value.equals("off")) {
            return false;
        }
        return defaultValue;
    }
}
