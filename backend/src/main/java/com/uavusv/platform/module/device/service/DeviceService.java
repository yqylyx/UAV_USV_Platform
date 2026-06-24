package com.uavusv.platform.module.device.service;

import com.uavusv.platform.common.api.PageResponse;
import com.uavusv.platform.module.device.dto.request.DeviceSaveRequest;
import com.uavusv.platform.module.device.dto.response.DeviceResponse;
import com.uavusv.platform.module.device.entity.DeviceStatus;
import com.uavusv.platform.module.device.entity.DeviceType;

public interface DeviceService {

    PageResponse<DeviceResponse> listDevices(
            String keyword,
            DeviceType type,
            DeviceStatus status,
            int page,
            int size
    );

    DeviceResponse getDevice(Long id);

    DeviceResponse createDevice(DeviceSaveRequest request);

    DeviceResponse updateDevice(Long id, DeviceSaveRequest request);

    void deleteDevice(Long id);
}
