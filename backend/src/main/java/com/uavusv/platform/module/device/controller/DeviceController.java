package com.uavusv.platform.module.device.controller;

import com.uavusv.platform.common.api.ApiResponse;
import com.uavusv.platform.common.api.PageResponse;
import com.uavusv.platform.module.device.dto.request.DeviceSaveRequest;
import com.uavusv.platform.module.device.dto.response.DeviceResponse;
import com.uavusv.platform.module.device.entity.DeviceStatus;
import com.uavusv.platform.module.device.entity.DeviceType;
import com.uavusv.platform.module.device.service.DeviceService;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/devices")
public class DeviceController {

    private final DeviceService deviceService;

    public DeviceController(DeviceService deviceService) {
        this.deviceService = deviceService;
    }

    @GetMapping
    public ApiResponse<PageResponse<DeviceResponse>> listDevices(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) DeviceType type,
            @RequestParam(required = false) DeviceStatus status,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size
    ) {
        return ApiResponse.success(deviceService.listDevices(keyword, type, status, page, size));
    }

    @GetMapping("/{id}")
    public ApiResponse<DeviceResponse> getDevice(@PathVariable Long id) {
        return ApiResponse.success(deviceService.getDevice(id));
    }

    @PostMapping
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<DeviceResponse> createDevice(@Valid @RequestBody DeviceSaveRequest request) {
        return ApiResponse.success(deviceService.createDevice(request));
    }

    @PutMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<DeviceResponse> updateDevice(
            @PathVariable Long id,
            @Valid @RequestBody DeviceSaveRequest request
    ) {
        return ApiResponse.success(deviceService.updateDevice(id, request));
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<Void> deleteDevice(@PathVariable Long id) {
        deviceService.deleteDevice(id);
        return ApiResponse.<Void>success(null);
    }
}
