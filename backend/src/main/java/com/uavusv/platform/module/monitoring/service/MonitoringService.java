package com.uavusv.platform.module.monitoring.service;

import com.uavusv.platform.module.device.entity.DeviceStatus;
import com.uavusv.platform.module.device.entity.DeviceType;
import com.uavusv.platform.module.monitoring.dto.response.RuntimeNodeResponse;
import com.uavusv.platform.module.monitoring.dto.response.RuntimeSummaryResponse;

import java.util.List;

public interface MonitoringService {

    RuntimeSummaryResponse getSummary();

    List<RuntimeNodeResponse> listRuntimeNodes(DeviceType type, DeviceStatus status);
}
