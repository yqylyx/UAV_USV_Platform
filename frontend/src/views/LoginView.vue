<script setup lang="ts">
import { Anchor, ArrowRight, LockKeyhole, UserRound } from '@lucide/vue'
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import missionOcean from '@/assets/mission-ocean.png'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()

const form = reactive({
  username: '',
  password: '',
})
const errorMessage = ref('')

async function submitLogin() {
  errorMessage.value = ''
  if (!form.username.trim() || !form.password) {
    errorMessage.value = '请输入用户名和密码'
    return
  }

  try {
    await authStore.login({
      username: form.username.trim(),
      password: form.password,
    })
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.replace(redirect)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登录失败，请稍后重试'
  }
}
</script>

<template>
  <main
    class="login-page"
    :style="{ backgroundImage: `url(${missionOcean})` }"
  >
    <section class="login-panel" aria-labelledby="login-title">
      <div class="login-brand">
        <span class="login-brand-mark"><Anchor :size="22" /></span>
        <span>
          <strong>UAV-USV</strong>
          <small>协同任务控制平台</small>
        </span>
      </div>

      <div class="login-heading">
        <p>MISSION CONTROL</p>
        <h1 id="login-title">海空协同，智能围捕</h1>
        <span>登录后进入任务控制台</span>
      </div>

      <form @submit.prevent="submitLogin">
        <label for="username">用户名</label>
        <el-input
          id="username"
          v-model="form.username"
          :prefix-icon="UserRound"
          size="large"
          autocomplete="username"
          placeholder="请输入用户名"
        />

        <label for="password">密码</label>
        <el-input
          id="password"
          v-model="form.password"
          :prefix-icon="LockKeyhole"
          type="password"
          size="large"
          autocomplete="current-password"
          placeholder="请输入密码"
          show-password
          @keyup.enter="submitLogin"
        />

        <el-alert
          v-if="errorMessage"
          :title="errorMessage"
          type="error"
          :closable="false"
          show-icon
        />

        <el-button
          native-type="submit"
          type="primary"
          size="large"
          :loading="authStore.loading"
          class="login-submit"
        >
          进入控制台
          <ArrowRight :size="17" />
        </el-button>
      </form>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  position: relative;
  display: grid;
  min-height: 100vh;
  place-items: center;
  padding: 28px;
  overflow: hidden;
  background-color: #10262f;
  background-position: center;
  background-size: cover;
}

.login-page::before {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(180deg, rgba(4, 17, 23, 0.28), rgba(4, 17, 23, 0.48)),
    linear-gradient(90deg, rgba(4, 17, 23, 0.2), rgba(4, 17, 23, 0.38));
  content: "";
}

.login-panel {
  position: relative;
  z-index: 1;
  width: min(100%, 420px);
  padding: 30px 32px 32px;
  color: #172126;
  background: rgba(248, 251, 251, 0.96);
  border: 1px solid rgba(255, 255, 255, 0.62);
  border-radius: 8px;
  box-shadow: 0 26px 80px rgba(1, 13, 18, 0.42);
  backdrop-filter: blur(16px);
}

.login-brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 11px;
}

.login-brand-mark {
  display: grid;
  width: 40px;
  height: 40px;
  place-items: center;
  color: #08252c;
  background: #62d6c4;
  border-radius: 6px;
}

.login-brand strong,
.login-brand small {
  display: block;
  letter-spacing: 0;
}

.login-brand strong {
  color: #18282d;
  font-size: 15px;
}

.login-brand small {
  margin-top: 2px;
  color: #72858a;
  font-size: 11px;
}

.login-heading {
  margin: 28px 0 25px;
  text-align: center;
}

.login-heading p {
  margin: 0 0 9px;
  color: #218d7c;
  font-size: 11px;
  font-weight: 700;
}

.login-heading h1 {
  margin: 0;
  color: #15252a;
  font-size: 26px;
  line-height: 1.25;
}

.login-heading span {
  display: block;
  margin-top: 9px;
  color: #718287;
  font-size: 12px;
}

.login-panel form {
  display: grid;
  gap: 11px;
}

.login-panel label {
  margin-top: 5px;
  color: #34484e;
  font-size: 13px;
  font-weight: 600;
}

.login-submit {
  width: 100%;
  margin-top: 11px;
}

.login-submit :deep(span) {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 560px) {
  .login-page {
    padding: 18px;
    background-position: 38% center;
  }

  .login-panel {
    padding: 26px 22px 28px;
  }

  .login-heading h1 {
    font-size: 23px;
  }
}
</style>
