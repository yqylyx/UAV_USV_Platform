package com.uavusv.platform.module.voiceintelligence;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.*;

import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Duration;

@SpringBootTest(
        classes = AsrEmbeddedTests.Config.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
            "app.voiceintelligence.enabled=true",
            "spring.servlet.multipart.location=${java.io.tmpdir}/asr-no-spool-test",
            "spring.servlet.multipart.file-size-threshold=0"
        })
class AsrEmbeddedTests {
    @SpringBootConfiguration
    @EnableAutoConfiguration(
            exclude = {
                org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration.class,
                org.springframework.boot.autoconfigure.orm.jpa.HibernateJpaAutoConfiguration.class,
                org.springframework.boot.autoconfigure.flyway.FlywayAutoConfiguration.class
            })
    @Import({
        AsrHttpTests.Config.class,
        AsrIngressFilter.class,
        AsrUploadFilter.class,
        AsrTransportConfig.class,
        com.uavusv.platform.module.auth.controller.AuthController.class
    })
    static class Config {}

    record Login(HttpClient client, String cookie, String csrfName, String csrf) {}

    Login login() throws Exception {
        var cookies = new java.net.CookieManager(null, java.net.CookiePolicy.ACCEPT_ALL);
        var client = HttpClient.newBuilder().cookieHandler(cookies).build();
        String base = "http://127.0.0.1:" + port;
        var login =
                client.send(
                        HttpRequest.newBuilder(URI.create(base + "/api/auth/login"))
                                .header("Content-Type", "application/json")
                                .POST(
                                        HttpRequest.BodyPublishers.ofString(
                                                "{\"username\":\"admin\",\"password\":\"test-only\"}"))
                                .build(),
                        HttpResponse.BodyHandlers.ofString());
        assertEquals(200, login.statusCode(), login.body());
        var response =
                client.send(
                        HttpRequest.newBuilder(URI.create(base + "/api/auth/csrf")).GET().build(),
                        HttpResponse.BodyHandlers.ofString());
        var token =
                new com.fasterxml.jackson.databind.ObjectMapper()
                        .readTree(response.body())
                        .path("data");
        String cookie =
                cookies.getCookieStore().getCookies().stream()
                        .map(c -> c.getName() + "=" + c.getValue())
                        .collect(java.util.stream.Collectors.joining("; "));
        return new Login(
                client, cookie, token.path("headerName").asText(), token.path("token").asText());
    }

    @LocalServerPort int port;
    @Autowired SpeechProvider provider;

    @Test
    void actualServletDoesNotSpoolMultipart() throws Exception {
        var dir = Path.of(System.getProperty("java.io.tmpdir"), "asr-no-spool-test");
        Files.createDirectories(dir);
        long before;
        try (var f = Files.list(dir)) {
            before = f.count();
        }
        var login = login();
        String id = java.util.UUID.randomUUID().toString();
        byte[] body = AudioMultipartTests.body(id, "audio/mpeg", new byte[1024 * 1024]);
        var req =
                HttpRequest.newBuilder(
                                URI.create("http://127.0.0.1:" + port + AsrIngressFilter.PATH))
                        .timeout(Duration.ofSeconds(10))
                        .header("Content-Type", "multipart/form-data; boundary=b")
                        .header("X-Request-ID", id)
                        .header("Idempotency-Key", id)
                        .header(login.csrfName(), login.csrf())
                        .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                        .build();
        var response = login.client().send(req, HttpResponse.BodyHandlers.ofString());
        assertEquals(200, response.statusCode(), response.body());
        assertTrue(response.body().contains("停止任务"));
        try (var f = Files.list(dir)) {
            assertEquals(before, f.count());
        }
    }

    @Test
    void stalledUploadHasBoundedTimeout() throws Exception {
        var login = login();
        try (var socket = new Socket("127.0.0.1", port)) {
            socket.setSoTimeout(15000);
            String id = java.util.UUID.randomUUID().toString();
            String headers =
                    "POST "
                            + AsrIngressFilter.PATH
                            + " HTTP/1.1\r\nHost: localhost\r\nCookie: "
                            + login.cookie()
                            + "\r\n"
                            + login.csrfName()
                            + ": "
                            + login.csrf()
                            + "\r\nContent-Type: multipart/form-data; boundary=b\r\nX-Request-ID: "
                            + id
                            + "\r\nIdempotency-Key: "
                            + id
                            + "\r\nContent-Length: 10000\r\nConnection: close\r\n\r\n--b\r\n";
            socket.getOutputStream().write(headers.getBytes(StandardCharsets.US_ASCII));
            socket.getOutputStream().flush();
            long started = System.nanoTime();
            String response =
                    new String(socket.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
            assertTrue(Duration.ofNanos(System.nanoTime() - started).toSeconds() < 15);
            assertTrue(response.contains("408"), response);
        }
    }
}
