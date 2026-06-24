CREATE TABLE mission_device (
    id BIGINT NOT NULL AUTO_INCREMENT,
    code VARCHAR(64) NOT NULL,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    host VARCHAR(128) NULL,
    port INT NULL,
    ros_namespace VARCHAR(128) NULL,
    description VARCHAR(500) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_mission_device_code (code),
    KEY idx_mission_device_type (type),
    KEY idx_mission_device_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO mission_device (code, name, type, status, host, port, ros_namespace, description)
VALUES
    ('uav-01', '协同无人机', 'UAV', 'OFFLINE', '127.0.0.1', NULL, '/uav_01', '从无人艇甲板起飞并执行围捕任务'),
    ('usv-01', '协同无人艇', 'USV', 'OFFLINE', '127.0.0.1', NULL, '/usv_01', '搭载无人机并朝目标灯塔方向航行'),
    ('lighthouse-01', '导航灯塔', 'LIGHTHOUSE', 'ONLINE', NULL, NULL, '/lighthouse_01', '海上围捕与导航目标'),
    ('ros-bridge-01', 'ROS2桥接节点', 'ROS_NODE', 'UNKNOWN', '127.0.0.1', 10000, '/ros_tcp_endpoint', '负责 ROS2 与 Unity 的消息桥接'),
    ('unity-client-01', 'Unity仿真端', 'UNITY_NODE', 'UNKNOWN', '127.0.0.1', 5174, NULL, '展示海洋、无人艇、无人机与灯塔状态');
