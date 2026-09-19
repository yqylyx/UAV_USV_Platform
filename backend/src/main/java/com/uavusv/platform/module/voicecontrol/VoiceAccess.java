package com.uavusv.platform.module.voicecontrol;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component
public class VoiceAccess {
    private final JdbcTemplate jdbc;

    public VoiceAccess(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public long user(boolean admin) {
        var auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || !auth.isAuthenticated() || "anonymousUser".equals(auth.getPrincipal()))
            throw new VoiceFailure(401, "UNAUTHORIZED");
        var rows =
                jdbc.queryForList(
                        "SELECT id,role,enabled FROM app_user WHERE username=?", auth.getName());
        if (rows.isEmpty()) throw new VoiceFailure(401, "UNAUTHORIZED");
        long id = ((Number) rows.get(0).get("id")).longValue();
        require(id, admin);
        return id;
    }

    public void require(long id, boolean admin) {
        var rows = jdbc.queryForList("SELECT role FROM app_user WHERE id=? AND enabled=true", id);
        if (rows.isEmpty() || (admin && !"ADMIN".equals(rows.get(0).get("role"))))
            throw new VoiceFailure(403, "FORBIDDEN");
    }
}
