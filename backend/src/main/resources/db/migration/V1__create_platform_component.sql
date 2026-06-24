CREATE TABLE platform_component (
    id BIGINT NOT NULL AUTO_INCREMENT,
    code VARCHAR(64) NOT NULL,
    name VARCHAR(100) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_platform_component_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO platform_component (code, name, status)
VALUES
    ('backend', 'Spring Boot 后端', 'READY'),
    ('database', 'MySQL 数据库', 'READY'),
    ('frontend', 'Vue 前端', 'READY'),
    ('ros2', 'ROS2 网关', 'PENDING'),
    ('unity', 'Unity 仿真端', 'PENDING');

