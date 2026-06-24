package com.uavusv.platform.module.system.service;

import com.uavusv.platform.module.system.dto.response.PlatformComponentResponse;
import com.uavusv.platform.module.system.dto.response.SystemHealthResponse;

import java.util.List;

public interface SystemService {

    SystemHealthResponse getHealth();

    List<PlatformComponentResponse> listComponents();
}
