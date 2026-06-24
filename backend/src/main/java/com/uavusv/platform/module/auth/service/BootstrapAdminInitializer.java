package com.uavusv.platform.module.auth.service;

import com.uavusv.platform.module.auth.entity.AppUser;
import com.uavusv.platform.module.auth.entity.UserRole;
import com.uavusv.platform.module.auth.repository.AppUserRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class BootstrapAdminInitializer implements ApplicationRunner {

    private final AppUserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final String username;
    private final String password;

    public BootstrapAdminInitializer(
            AppUserRepository userRepository,
            PasswordEncoder passwordEncoder,
            @Value("${app.security.bootstrap-admin.username}") String username,
            @Value("${app.security.bootstrap-admin.password}") String password
    ) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.username = username;
        this.password = password;
    }

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        if (userRepository.existsByUsername(username)) {
            return;
        }

        userRepository.save(new AppUser(
                username,
                passwordEncoder.encode(password),
                "系统管理员",
                UserRole.ADMIN
        ));
    }
}
