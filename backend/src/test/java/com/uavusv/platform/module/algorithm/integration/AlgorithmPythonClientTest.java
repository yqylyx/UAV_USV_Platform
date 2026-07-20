package com.uavusv.platform.module.algorithm.integration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.jsonPath;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class AlgorithmPythonClientTest {

    private MockRestServiceServer server;
    private AlgorithmPythonClient client;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder().baseUrl("http://algorithm-service.test");
        server = MockRestServiceServer.bindTo(builder).build();
        client = new AlgorithmPythonClient(builder.build());
    }

    @Test
    void healthCallsHealthEndpointAndParsesStatus() {
        server.expect(once(), requestTo("http://algorithm-service.test/health"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess("{\"status\":\"ok\"}", MediaType.APPLICATION_JSON));

        AlgorithmPythonClient.HealthResponse response = client.health();

        assertEquals("ok", response.status());
        server.verify();
    }

    @Test
    void runOncePostsPythonRequestWithoutGeneratedDefaultsAndParsesResponse() throws Exception {
        server.expect(once(), requestTo("http://algorithm-service.test/api/v1/algorithms/run-once"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().contentType(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.commandId").value("alg-001"))
                .andExpect(jsonPath("$.algorithmType").value("CAPTURE"))
                .andExpect(jsonPath("$.targetPosition.x").value(50.0))
                .andExpect(jsonPath("$.targetPosition.y").value(60.0))
                .andExpect(jsonPath("$.targetPosition.z").value(0.0))
                .andExpect(jsonPath("$.targetPosition.heading").value(1.5))
                .andExpect(jsonPath("$.uavs[0].vehicleId").value("uav_01"))
                .andExpect(jsonPath("$.uavs[0].position.x").value(1.0))
                .andExpect(jsonPath("$.uavs[0].position.y").value(2.0))
                .andExpect(jsonPath("$.uavs[0].position.z").value(30.0))
                .andExpect(jsonPath("$.usvs[0].vehicleId").value("usv_01"))
                .andExpect(jsonPath("$.usvs[0].position.x").value(10.0))
                .andExpect(jsonPath("$.usvs[0].position.y").value(20.0))
                .andRespond(withSuccess("""
                        {
                          "commandId": "alg-001",
                          "algorithmType": "CAPTURE",
                          "status": "RUNNING",
                          "stage": "capture-step-completed",
                          "targetId": "target_01",
                          "assignments": [
                            {
                              "vehicleId": "uav_01",
                              "vehicleCode": "uav-01",
                              "role": "TRACK",
                              "x": 11.0,
                              "y": 22.0,
                              "z": 33.0,
                              "heading": 0.25,
                              "detail": {"source": "python", "score": 0.93}
                            }
                          ],
                          "events": [
                            {
                              "level": "INFO",
                              "stage": "capture-step-completed",
                              "message": "one step completed",
                              "detail": {"iterations": 1}
                            }
                          ],
                          "metrics": {"objective": 12.5, "valid": true}
                        }
                        """, MediaType.APPLICATION_JSON));

        AlgorithmPythonClient.AlgorithmResult response = client.runOnce(sampleRequest());

        assertEquals("alg-001", response.commandId());
        assertEquals("RUNNING", response.status());
        assertEquals(1, response.assignments().size());
        AlgorithmPythonClient.Assignment assignment = response.assignments().get(0);
        assertEquals("uav_01", assignment.vehicleId());
        assertEquals("TRACK", assignment.role());
        assertEquals("python", assignment.detail().path("source").asText());
        assertEquals(0.93, assignment.detail().path("score").asDouble());
        assertEquals(1, response.events().size());
        assertEquals("one step completed", response.events().get(0).message());
        assertEquals(1, response.events().get(0).detail().path("iterations").asInt());
        assertEquals(12.5, response.metrics().path("objective").asDouble());
        assertEquals(true, response.metrics().path("valid").asBoolean());
        assertDetailIsObject(assignment.detail());
        server.verify();
    }

    @Test
    void runOnceThrowsOnFourHundredResponse() {
        server.expect(once(), requestTo("http://algorithm-service.test/api/v1/algorithms/run-once"))
                .andExpect(method(HttpMethod.POST))
                .andRespond(withStatus(HttpStatus.BAD_REQUEST)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body("{\"detail\":\"invalid request\"}"));

        assertThrows(AlgorithmPythonClient.AlgorithmPythonClientException.class,
                () -> client.runOnce(sampleRequest()));
        server.verify();
    }

    @Test
    void runOnceThrowsOnFiveHundredResponse() {
        server.expect(once(), requestTo("http://algorithm-service.test/api/v1/algorithms/run-once"))
                .andExpect(method(HttpMethod.POST))
                .andRespond(withStatus(HttpStatus.INTERNAL_SERVER_ERROR)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body("{\"detail\":\"service failed\"}"));

        assertThrows(AlgorithmPythonClient.AlgorithmPythonClientException.class,
                () -> client.runOnce(sampleRequest()));
        server.verify();
    }

    private AlgorithmPythonClient.RunOnceRequest sampleRequest() {
        return new AlgorithmPythonClient.RunOnceRequest(
                "alg-001",
                "CAPTURE",
                "target_01",
                new AlgorithmPythonClient.Position(50.0, 60.0, 0.0, 1.5),
                "threat_01",
                new AlgorithmPythonClient.Position(70.0, 80.0, 0.0, 2.5),
                List.of(new AlgorithmPythonClient.Vehicle(
                        "uav_01",
                        "uav-01",
                        new AlgorithmPythonClient.Position(1.0, 2.0, 30.0, 0.5)
                )),
                List.of(new AlgorithmPythonClient.Vehicle(
                        "usv_01",
                        "usv-01",
                        new AlgorithmPythonClient.Position(10.0, 20.0, 0.0, 0.75)
                )),
                Map.of("maxIterations", 1, "mode", "test")
        );
    }

    private void assertDetailIsObject(JsonNode detail) throws Exception {
        assertNotNull(detail);
        assertEquals("object", new ObjectMapper().readTree(detail.toString()).getNodeType().name().toLowerCase());
    }
}
