package com.uavusv.platform.module.visualsensor;

import com.uavusv.platform.module.visualsensor.service.VisualSensorService;
import org.junit.jupiter.api.Test;

import java.util.Base64;

import static org.assertj.core.api.Assertions.assertThat;

class VisualSensorServiceTests {

    @Test
    void exposesSixWaitingChannelsWithoutFabricatingOnlineFrames() {
        VisualSensorService service = new VisualSensorService();

        var overview = service.overview();

        assertThat(overview.totalCount()).isEqualTo(6);
        assertThat(overview.onlineCount()).isZero();
        assertThat(overview.sensors())
                .extracting(sensor -> sensor.cameraId())
                .containsExactly("uav_01", "uav_02", "uav_03", "usv_01", "usv_02", "usv_03");
        assertThat(overview.sensors()).allMatch(sensor -> "WAITING".equals(sensor.status()));
    }

    @Test
    void storesRealJpegAndMarksOnlyThatChannelOnline() {
        VisualSensorService service = new VisualSensorService();
        byte[] jpeg = {(byte) 0xff, (byte) 0xd8, 1, 2, (byte) 0xff, (byte) 0xd9};

        service.observeJpegFrame(
                "uav_01",
                Base64.getEncoder().encodeToString(jpeg),
                640,
                360,
                System.currentTimeMillis(),
                0.02
        );

        var overview = service.overview();
        assertThat(overview.onlineCount()).isEqualTo(1);
        assertThat(overview.sensors().get(0).status()).isEqualTo("ONLINE");
        assertThat(overview.sensors().get(0).width()).isEqualTo(640);
        assertThat(service.latestFrame("uav_01")).hasValueSatisfying(
                stored -> assertThat(stored).isEqualTo(jpeg)
        );
    }
}
