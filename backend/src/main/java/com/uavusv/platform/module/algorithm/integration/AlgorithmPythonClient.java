package com.uavusv.platform.module.algorithm.integration;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

import java.util.List;
import java.util.Map;
import java.util.function.Supplier;

@Component
public class AlgorithmPythonClient {

    private final RestClient restClient;

    @Autowired
    public AlgorithmPythonClient(
            RestClient.Builder restClientBuilder,
            @Value("${app.algorithm.service-base-url}") String serviceBaseUrl
    ) {
        this(restClientBuilder.baseUrl(serviceBaseUrl).build());
    }

    AlgorithmPythonClient(RestClient restClient) {
        this.restClient = restClient;
    }

    public HealthResponse health() {
        return call("health", () -> restClient.get()
                .uri("/health")
                .retrieve()
                .body(HealthResponse.class));
    }

    public AlgorithmResult runOnce(RunOnceRequest request) {
        return call("run-once", () -> restClient.post()
                .uri("/api/v1/algorithms/run-once")
                .contentType(MediaType.APPLICATION_JSON)
                .body(request)
                .retrieve()
                .body(AlgorithmResult.class));
    }

    private <T> T call(String operation, Supplier<T> supplier) {
        try {
            T response = supplier.get();
            if (response == null) {
                throw new AlgorithmPythonClientException("Python algorithm service returned an empty response for " + operation);
            }
            return response;
        } catch (RestClientResponseException exception) {
            throw new AlgorithmPythonClientException(
                    "Python algorithm service returned HTTP " + exception.getStatusCode() + " for " + operation,
                    exception
            );
        } catch (RestClientException exception) {
            throw new AlgorithmPythonClientException(
                    "Failed to call Python algorithm service for " + operation + ": " + exception.getMessage(),
                    exception
            );
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record HealthResponse(String status) {
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record RunOnceRequest(
            String commandId,
            String algorithmType,
            String targetId,
            Position targetPosition,
            String threatTargetId,
            Position threatPosition,
            List<Vehicle> uavs,
            List<Vehicle> usvs,
            Map<String, Object> parameters
    ) {
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record Vehicle(
            String vehicleId,
            String vehicleCode,
            Position position
    ) {
    }

    public record Position(
            double x,
            double y,
            double z,
            double heading
    ) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record AlgorithmResult(
            String commandId,
            String algorithmType,
            String status,
            String stage,
            String targetId,
            List<Assignment> assignments,
            List<AlgorithmEvent> events,
            JsonNode metrics,
            String message,
            String error,
            JsonNode detail
    ) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Assignment(
            String vehicleId,
            String vehicleCode,
            String role,
            double x,
            double y,
            double z,
            double heading,
            JsonNode detail
    ) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record AlgorithmEvent(
            String level,
            String stage,
            String message,
            JsonNode detail
    ) {
    }

    public static class AlgorithmPythonClientException extends RuntimeException {
        public AlgorithmPythonClientException(String message) {
            super(message);
        }

        public AlgorithmPythonClientException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
