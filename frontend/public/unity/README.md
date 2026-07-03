# Unity WebGL 部署说明

系统总览页会从这里加载 Unity WebGL：

- /unity/Build/UAV_USV_WebGL.loader.js
- /unity/Build/UAV_USV_WebGL.data
- /unity/Build/UAV_USV_WebGL.framework.js
- /unity/Build/UAV_USV_WebGL.wasm

推荐打包方式：

1. 打开 Unity Hub。
2. 给 Unity 2022.3.57f1 安装 WebGL Build Support。
3. 打开项目：F:/Unity/Projects/unity_ws。
4. 菜单选择：UAV-USV -> Build WebGL For Vue。
5. 构建完成后，Build 目录会自动生成在本目录下。
6. 回到前端运行 npm run dev，进入系统总览页查看 Unity 场景。

浏览器 GPU：

- Chrome / Edge 打开硬件加速。
- Windows 设置 -> 系统 -> 显示 -> 图形，将浏览器设为高性能 GPU。
- 在 chrome://gpu 或 edge://gpu 确认 WebGL / WebGL2 启用。
