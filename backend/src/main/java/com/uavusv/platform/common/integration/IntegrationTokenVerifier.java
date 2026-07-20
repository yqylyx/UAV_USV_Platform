package com.uavusv.platform.common.integration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

@Component
public class IntegrationTokenVerifier {

    private final byte[] expectedToken;

    public IntegrationTokenVerifier(@Value("${app.integration.token}") String expectedToken) {
        this.expectedToken = expectedToken.getBytes(StandardCharsets.UTF_8);
    }

    public void verifyAuthenticatedOrToken(Authentication authentication, String token) {
        if (isAuthenticatedUser(authentication)) {
            return;
        }
        if (token != null && MessageDigest.isEqual(expectedToken, token.getBytes(StandardCharsets.UTF_8))) {
            return;
        }
        throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Invalid integration token");
    }

    private boolean isAuthenticatedUser(Authentication authentication) {
        return authentication != null
                && authentication.isAuthenticated()
                && !(authentication instanceof AnonymousAuthenticationToken);
    }
}
