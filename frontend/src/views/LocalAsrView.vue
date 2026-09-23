<script setup lang="ts">
import ConsoleLayout from '@/components/layout/ConsoleLayout.vue'
import LocalAsrInput from '@/components/voice/LocalAsrInput.vue'
import { useAuthStore } from '@/stores/auth'
const auth = useAuthStore()
const enabled = import.meta.env.VITE_VOICE_ASR_ONLY === 'true'
</script>
<template>
  <ConsoleLayout title="本地语音识别" eyebrow="LOCAL ASR · D1" :show-refresh="false">
    <div class="asr-page">
      <LocalAsrInput v-if="enabled" :operator-scope="`${auth.user?.username ?? ''}:${auth.user?.role ?? ''}`" :disabled="auth.user?.role !== 'ADMIN' || auth.loading" />
      <p v-else>本地语音识别入口未启用，请由联调人员确认配置；不会自动切换到Mock。</p>
    </div>
  </ConsoleLayout>
</template>
<style scoped>.asr-page { width:min(780px, 100%); margin:24px auto; }</style>
