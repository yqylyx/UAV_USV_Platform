package com.uavusv.platform.module.auth.dto.response;

import org.springframework.security.core.Authentication;

public record CurrentUserResponse(
        String username,
        String role
) {
    public static CurrentUserResponse from(Authentication authentication) {
        String role = authentication.getAuthorities().stream()
                .findFirst()
                .map(authority -> authority.getAuthority().replaceFirst("^ROLE_", ""))
                .orElse("VIEWER");
        return new CurrentUserResponse(authentication.getName(), role);
    }
}
