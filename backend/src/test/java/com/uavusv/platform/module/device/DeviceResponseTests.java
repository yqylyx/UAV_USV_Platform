package com.uavusv.platform.module.device;

import com.uavusv.platform.module.device.dto.response.DeviceResponse;
import com.uavusv.platform.module.device.entity.Device;
import com.uavusv.platform.module.device.entity.DeviceStatus;
import com.uavusv.platform.module.device.entity.DeviceType;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class DeviceResponseTests {

    @Test
    void responseKeepsCoreDeviceFields() {
        Device device = new Device(
                "uav-test",
                "测试无人机",
                DeviceType.UAV,
                DeviceStatus.ONLINE,
                "127.0.0.1",
                10001,
                "/uav_test",
                "test"
        );

        DeviceResponse response = DeviceResponse.from(device);

        assertThat(response.code()).isEqualTo("uav-test");
        assertThat(response.name()).isEqualTo("测试无人机");
        assertThat(response.type()).isEqualTo(DeviceType.UAV);
        assertThat(response.status()).isEqualTo(DeviceStatus.ONLINE);
        assertThat(response.rosNamespace()).isEqualTo("/uav_test");
    }
}
