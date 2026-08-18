package com.uavusv.platform.module.visualsensor.controller;

import com.uavusv.platform.common.api.ApiResponse;
import com.uavusv.platform.module.visualsensor.dto.VisualSensorOverviewResponse;
import com.uavusv.platform.module.visualsensor.service.VisualSensorService;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/visual-sensors")
public class VisualSensorController {

    private final VisualSensorService visualSensorService;

    public VisualSensorController(VisualSensorService visualSensorService) {
        this.visualSensorService = visualSensorService;
    }

    @GetMapping
    public ApiResponse<VisualSensorOverviewResponse> overview() {
        return ApiResponse.success(visualSensorService.overview());
    }

    @PostMapping("/{cameraId}/focus")
    public ApiResponse<VisualSensorOverviewResponse> focus(@PathVariable String cameraId) {
        visualSensorService.focus(cameraId);
        return ApiResponse.success(visualSensorService.overview());
    }

    @GetMapping(value = "/{cameraId}/frame", produces = MediaType.IMAGE_JPEG_VALUE)
    public ResponseEntity<byte[]> frame(@PathVariable String cameraId) {
        return visualSensorService.latestFrame(cameraId)
                .map(bytes -> ResponseEntity.ok()
                        .cacheControl(CacheControl.noStore())
                        .header(HttpHeaders.PRAGMA, "no-cache")
                        .contentType(MediaType.IMAGE_JPEG)
                        .body(bytes))
                .orElseGet(() -> ResponseEntity.status(HttpStatus.NO_CONTENT)
                        .cacheControl(CacheControl.noStore())
                        .build());
    }
}
