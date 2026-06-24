package com.uavusv.platform.common.api;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ApiResponseTests {

    @Test
    void successContainsPayloadAndStandardMetadata() {
        ApiResponse<String> response = ApiResponse.success("ready");

        assertThat(response.code()).isEqualTo("SUCCESS");
        assertThat(response.message()).isEqualTo("操作成功");
        assertThat(response.data()).isEqualTo("ready");
        assertThat(response.timestamp()).isNotNull();
    }

    @Test
    void failureDoesNotExposeADataPayload() {
        ApiResponse<Void> response = ApiResponse.failure("COMMON_400", "参数错误");

        assertThat(response.code()).isEqualTo("COMMON_400");
        assertThat(response.message()).isEqualTo("参数错误");
        assertThat(response.data()).isNull();
    }
}
