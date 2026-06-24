package com.uavusv.platform.module.auth.dto.response;

public record CsrfTokenResponse(
        String headerName,
        String parameterName,
        String token
) {
}
