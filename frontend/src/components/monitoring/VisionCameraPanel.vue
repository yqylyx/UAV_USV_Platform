<script setup lang="ts">
import { computed, ref } from 'vue'

import { getVisionCameraSources } from '@/services/visionDataService'

const cameraSources = getVisionCameraSources()

const selectedSensorId = ref(cameraSources[0]?.sensorId ?? '')

const selectedCamera = computed(() =>
  cameraSources.find((camera) => camera.sensorId === selectedSensorId.value),
)
</script>

<template>
  <section class="console-panel vision-camera-panel">
    <div class="vision-camera-heading">
      <div>
        <h2>相机监控</h2>
        <p>查看无人机视觉传感器画面及对应ROS图像来源。</p>
      </div>

      <el-select
        v-model="selectedSensorId"
        class="camera-selector"
        placeholder="选择相机"
      >
        <el-option
          v-for="camera in cameraSources"
          :key="camera.sensorId"
          :label="camera.displayName"
          :value="camera.sensorId"
        />
      </el-select>
    </div>

    <div v-if="selectedCamera" class="camera-content">
      <div class="camera-preview">
        <div class="camera-placeholder">
          <span class="camera-symbol">CAM</span>
          <strong>视频流尚未接入</strong>
          <p>当前已完成前端视频窗口，等待ROS图像转换为浏览器可播放的视频流。</p>
        </div>

        <div class="camera-overlay camera-overlay-top">
          <el-tag
            :type="selectedCamera.online ? 'success' : 'danger'"
            effect="dark"
          >
            {{ selectedCamera.online ? '传感器在线' : '传感器离线' }}
          </el-tag>
        </div>

        <div class="camera-overlay camera-overlay-bottom">
          {{ selectedCamera.displayName }}
        </div>
      </div>

      <aside class="camera-information">
        <h3>视频源信息</h3>

        <dl>
          <div>
            <dt>载具编号</dt>
            <dd>{{ selectedCamera.vehicleId }}</dd>
          </div>

          <div>
            <dt>传感器编号</dt>
            <dd>{{ selectedCamera.sensorId }}</dd>
          </div>

          <div>
            <dt>ROS图像Topic</dt>
            <dd :title="selectedCamera.topic">
              {{ selectedCamera.topic }}
            </dd>
          </div>

          <div>
            <dt>传感器状态</dt>
            <dd>{{ selectedCamera.online ? '在线' : '离线' }}</dd>
          </div>

          <div>
            <dt>浏览器视频流</dt>
            <dd>{{ selectedCamera.streamUrl ?? '尚未提供' }}</dd>
          </div>
        </dl>

        <el-alert
          title="等待视频桥接"
          description="ROS Image Topic不能直接由浏览器播放，需要后端、MJPEG、HLS或WebRTC服务提供视频地址。"
          type="info"
          show-icon
          :closable="false"
        />
      </aside>
    </div>

    <el-empty v-else description="暂无可用相机" />
  </section>
</template>

<style scoped>
.vision-camera-panel {
  margin-top: 20px;
  overflow: hidden;
}

.vision-camera-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.vision-camera-heading h2 {
  margin: 0;
  font-size: 18px;
}

.vision-camera-heading p {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.camera-selector {
  width: 220px;
}

.camera-content {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(280px, 0.8fr);
  gap: 18px;
}

.camera-preview {
  position: relative;
  min-height: 360px;
  overflow: hidden;
  border: 1px solid rgba(86, 207, 225, 0.3);
  border-radius: 10px;
  background:
    linear-gradient(rgba(10, 42, 48, 0.7), rgba(4, 20, 25, 0.9)),
    repeating-linear-gradient(
      0deg,
      transparent,
      transparent 39px,
      rgba(86, 207, 225, 0.08) 40px
    ),
    repeating-linear-gradient(
      90deg,
      transparent,
      transparent 39px,
      rgba(86, 207, 225, 0.08) 40px
    );
}

.camera-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px;
  color: #d8f5f7;
  text-align: center;
}

.camera-placeholder strong {
  margin-top: 14px;
  font-size: 20px;
}

.camera-placeholder p {
  max-width: 500px;
  margin: 10px 0 0;
  color: rgba(216, 245, 247, 0.65);
  line-height: 1.7;
}

.camera-symbol {
  display: grid;
  width: 72px;
  height: 72px;
  place-items: center;
  border: 1px solid rgba(86, 207, 225, 0.65);
  border-radius: 50%;
  color: #56cfe1;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 2px;
}

.camera-overlay {
  position: absolute;
  z-index: 1;
}

.camera-overlay-top {
  top: 16px;
  right: 16px;
}

.camera-overlay-bottom {
  right: 16px;
  bottom: 14px;
  left: 16px;
  color: rgba(216, 245, 247, 0.8);
  font-size: 13px;
}

.camera-information {
  padding: 18px;
  border: 1px solid rgba(86, 207, 225, 0.2);
  border-radius: 10px;
  background: rgba(8, 35, 40, 0.45);
}

.camera-information h3 {
  margin: 0 0 16px;
  font-size: 16px;
}

.camera-information dl {
  display: grid;
  gap: 12px;
  margin: 0 0 18px;
}

.camera-information dl div {
  min-width: 0;
}

.camera-information dt {
  margin-bottom: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.camera-information dd {
  margin: 0;
  overflow: hidden;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 900px) {
  .camera-content {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 600px) {
  .vision-camera-heading {
    flex-direction: column;
  }

  .camera-selector {
    width: 100%;
  }

  .camera-preview {
    min-height: 280px;
  }
}
</style>