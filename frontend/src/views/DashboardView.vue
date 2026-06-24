<script setup lang="ts">
import ConsoleLayout from '@/components/layout/ConsoleLayout.vue'

const assets = [
  { code: 'UAV-01', role: '高空侦察', detail: '目标视觉锁定 / 东北航线', type: 'air', status: 'READY' },
  { code: 'UAV-02', role: '侧翼压制', detail: '轨迹预测 / 西北航线', type: 'air', status: 'READY' },
  { code: 'UAV-03', role: '低空补盲', detail: '海面遮挡补偿 / 南向跟随', type: 'air', status: 'READY' },
  { code: 'USV-01', role: '正面拦截', detail: '主追踪艇 / 收敛航向', type: 'sea', status: 'READY' },
  { code: 'USV-02', role: '左翼封锁', detail: '速度匹配 / 半径约束', type: 'sea', status: 'READY' },
  { code: 'USV-03', role: '右翼封锁', detail: '水面包络 / 目标截断', type: 'sea', status: 'READY' },
]

const phases = [
  { step: '1', title: '目标发现', text: 'UAV 先行侦察，USV 接收目标航迹与速度估计。' },
  { step: '2', title: '协同分配', text: '算法服务按距离、角度和任务角色分配包围位置。' },
  { step: '3', title: '闭环围捕', text: 'Unity 显示态势，ROS2 持续反馈位姿，Web 统一控制任务。' },
]

const readouts = [
  { label: '围捕完成度', value: '72%', text: '包络半径持续收缩' },
  { label: '目标相对速度', value: '2.8 m/s', text: '预测航向稳定' },
  { label: '通信延迟', value: '38 ms', text: 'ROS2 / Unity 链路正常' },
  { label: '安全距离', value: '15.4 m', text: '未触发碰撞预警' },
]

const links = [
  { name: 'ROS2 / Gazebo', value: 88 },
  { name: 'WebSocket Bridge', value: 92 },
  { name: 'Unity Pose Sync', value: 84 },
  { name: 'Mission Control', value: 76 },
]

const architecture = [
  { layer: '5', title: '展示交互层', text: 'Vue 控制台 / Unity 三维态势', state: '已具备' },
  { layer: '4', title: '业务服务层', text: '设备、任务、状态、日志、评估', state: '建设中' },
  { layer: '3', title: '智能算法层', text: '识别、分配、路径规划、围捕控制', state: '待接入' },
  { layer: '2', title: '通信与认知层', text: 'ROS2 / WebSocket / 多源状态共享', state: '已打通' },
  { layer: '1', title: '仿真与执行层', text: 'Gazebo / UAV / USV / Unity 场景', state: '已打通' },
]

const units = [
  { code: 'UAV-01', number: '01', type: 'air', className: 'uav-a' },
  { code: 'UAV-02', number: '02', type: 'air', className: 'uav-b' },
  { code: 'UAV-03', number: '03', type: 'air', className: 'uav-c' },
  { code: 'USV-01', number: '01', type: 'sea', className: 'usv-a' },
  { code: 'USV-02', number: '02', type: 'sea', className: 'usv-b' },
  { code: 'USV-03', number: '03', type: 'sea', className: 'usv-c' },
]
</script>

<template>
  <ConsoleLayout title="系统总览" eyebrow="MISSION OVERVIEW">
    <section class="mission-overview" aria-label="海空协同围捕态势总览">
      <header class="mission-hero">
        <div>
          <p class="mission-kicker">UAV-USV COOPERATIVE ENCIRCLEMENT COMMAND</p>
          <h2>海空协同围捕态势总览</h2>
          <p>
            面向三无人机、三无人艇的目标围捕任务，融合 ROS2/Gazebo 仿真、Unity3D 三维态势与 Web 任务控制，
            形成感知、通信、决策、协同与展示的一体化控制闭环。
          </p>
        </div>
        <div class="mission-window">
          <span>任务窗口</span>
          <strong>03:18</strong>
          <small>目标锁定 / 六机协同闭环</small>
        </div>
      </header>

      <div class="mission-dashboard">
        <aside class="mission-panel">
          <div class="mission-panel-title">
            <h3>协同编队</h3>
            <span class="mission-tag">6 / 6 ONLINE</span>
          </div>
          <div class="mission-asset-grid">
            <div v-for="asset in assets" :key="asset.code" class="mission-asset-row">
              <div class="mission-asset-icon" :class="asset.type">
                {{ asset.type === 'air' ? 'UAV' : 'USV' }}
              </div>
              <div>
                <strong>{{ asset.code }} {{ asset.role }}</strong>
                <span>{{ asset.detail }}</span>
              </div>
              <small>{{ asset.status }}</small>
            </div>
          </div>

          <div class="mission-phase-list">
            <div v-for="phase in phases" :key="phase.step" class="mission-phase">
              <div class="mission-phase-index">{{ phase.step }}</div>
              <div>
                <strong>{{ phase.title }}</strong>
                <span>{{ phase.text }}</span>
              </div>
            </div>
          </div>
        </aside>

        <section class="mission-panel mission-tactical">
          <div class="mission-map-header">
            <div>
              <h3>数字海域态势图</h3>
              <p>三无人艇水面封锁，三无人机空中侦察，对目标形成双层包围圈。</p>
            </div>
            <div class="mission-signal"><i></i> ROS2 WebSocket</div>
            <div class="mission-signal"><i></i> Unity 3D Sync</div>
          </div>

          <div class="mission-sea-map" aria-label="三无人机三无人艇围捕目标示意">
            <div class="mission-sweep"></div>
            <div class="mission-range-ring"></div>
            <div v-for="index in 6" :key="index" class="mission-vector" :class="`v${index}`"></div>
            <div class="mission-target">TARGET</div>
            <div
              v-for="unit in units"
              :key="unit.code"
              class="mission-unit"
              :class="[unit.type, unit.className]"
            >
              <div class="mission-glyph">{{ unit.number }}</div>
              <span>{{ unit.code }}</span>
            </div>
          </div>

          <div class="mission-readouts">
            <div v-for="readout in readouts" :key="readout.label" class="mission-readout">
              <span>{{ readout.label }}</span>
              <strong>{{ readout.value }}</strong>
              <small>{{ readout.text }}</small>
            </div>
          </div>
        </section>

        <aside class="mission-panel">
          <div class="mission-panel-title">
            <h3>任务闭环</h3>
            <span class="mission-tag warn">DEMO MODE</span>
          </div>
          <div class="mission-status-stack">
            <div class="mission-status-card">
              <span>当前阶段</span>
              <strong>协同收缩</strong>
              <small>无人机提供目标航迹，无人艇按包围点位推进。</small>
            </div>
            <div class="mission-status-card">
              <span>指挥链路</span>
              <strong>Web -> Spring Boot -> ROS2</strong>
              <small>管理平台负责任务配置、节点状态和控制命令编排。</small>
            </div>
            <div class="mission-status-card">
              <span>三维态势</span>
              <strong>Unity3D 半实物可视化</strong>
              <small>同步 Gazebo 位姿，展示海面、舰艇、无人机和目标。</small>
            </div>
          </div>

          <div class="mission-panel-title compact">
            <h3>链路健康</h3>
            <span class="mission-tag">LOW LATENCY</span>
          </div>
          <div class="mission-link-stack">
            <div v-for="link in links" :key="link.name" class="mission-link-row">
              <span>{{ link.name }}</span>
              <div class="mission-bar"><i :style="{ width: `${link.value}%` }"></i></div>
            </div>
          </div>

          <div class="mission-architecture">
            <div v-for="item in architecture" :key="item.layer" class="mission-arch-layer">
              <b>{{ item.layer }}</b>
              <div>
                <strong>{{ item.title }}</strong>
                <span>{{ item.text }}</span>
              </div>
              <em>{{ item.state }}</em>
            </div>
          </div>

          <div class="mission-note">
            本页先作为任务态势入口，后续将逐步接入运行监控、任务管理、算法服务与 Unity 画面状态。
          </div>
        </aside>
      </div>
    </section>
  </ConsoleLayout>
</template>
