from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    ws_host = LaunchConfiguration('ws_host')
    ws_port = LaunchConfiguration('ws_port')

    return LaunchDescription([
        DeclareLaunchArgument(
            'ws_host',
            default_value='0.0.0.0',
            description='Visual sensor WebSocket listen address',
        ),
        DeclareLaunchArgument(
            'ws_port',
            default_value='8766',
            description='Visual sensor WebSocket listen port',
        ),
        Node(
            package='uav_usv_sim',
            executable='visual_sensor_websocket_bridge',
            name='visual_sensor_websocket_bridge',
            output='screen',
            parameters=[{
                'ws_host': ws_host,
                'ws_port': ParameterValue(ws_port, value_type=int),
            }],
        ),
    ])
