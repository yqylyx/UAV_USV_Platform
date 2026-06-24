package com.uavusv.platform.module.auth;

import com.uavusv.platform.module.auth.dto.response.CurrentUserResponse;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class AuthDtoTests {

    @Test
    void currentUserResponseRemovesSpringRolePrefix() {
        var authentication = new UsernamePasswordAuthenticationToken(
                "root",
                null,
                List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
        );

        CurrentUserResponse response = CurrentUserResponse.from(authentication);

        assertThat(response.username()).isEqualTo("root");
        assertThat(response.role()).isEqualTo("ADMIN");
    }
}
