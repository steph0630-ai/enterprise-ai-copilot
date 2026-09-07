<script setup>
// 登录/注册页（Day 12 登录注册，Day 13 改造：工号 + 姓名）
// 注意：
//  - 注册接口后端强制 role="employee"——普通注册者永远当不了管理员
//  - 登录只用工号 + 密码（姓名会重名，不能当登录凭据）
import { ref } from 'vue'

const emit = defineEmits(['login'])

const tab = ref('login')  // 'login' | 'register'

// ===== 登录表单 =====
const employeeNo = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

// ===== 注册表单 =====
const regEmployeeNo = ref('')
const regName = ref('')
const regPassword = ref('')
const regPhone = ref('')
const regEmail = ref('')
const regLoading = ref(false)
const regError = ref('')

// 登录 + 拉用户信息，返回 { access_token, me }（注册后自动登录也要用）
async function doLogin(account, p) {
  const res = await fetch('/api/v1/users/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ employee_no: account, password: p }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || `登录失败（HTTP ${res.status}）`)
  const me = await fetch('/api/v1/users/me', {
    headers: { Authorization: `Bearer ${data.access_token}` },
  }).then((r) => r.json())
  return { access_token: data.access_token, me }
}

async function submitLogin() {
  if (!employeeNo.value || !password.value) return
  loading.value = true
  error.value = ''
  try {
    const logged = await doLogin(employeeNo.value, password.value)
    emit('login', logged.access_token, logged.me)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function submitRegister() {
  if (!regEmployeeNo.value || !regName.value || !regPassword.value) return
  regLoading.value = true
  regError.value = ''
  try {
    // 1. 注册（角色后端强制 employee，这里不传 role）
    const res = await fetch('/api/v1/users/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        employee_no: regEmployeeNo.value,
        name: regName.value,
        password: regPassword.value,
        phone: regPhone.value || null,
        email: regEmail.value || null,
      }),
    })
    const data = await res.json()
    if (!res.ok) {
      throw new Error(Array.isArray(data.detail) ? '请检查填写内容' : data.detail || '注册失败')
    }
    // 2. 注册成功 → 自动登录，直接进系统
    const logged = await doLogin(regEmployeeNo.value, regPassword.value)
    emit('login', logged.access_token, logged.me)
  } catch (e) {
    regError.value = e.message
  } finally {
    regLoading.value = false
  }
}
</script>

<template>
  <div class="login">
    <h1>企业智能助手</h1>
    <p class="subtitle">企业知识问答与数据分析 Agent</p>

    <el-tabs v-model="tab" class="tabs" stretch>
      <!-- 登录：只用工号 + 密码 -->
      <el-tab-pane label="登录" name="login">
        <div class="form">
          <el-input v-model="employeeNo" placeholder="工号" size="large" />
          <el-input
            v-model="password"
            type="password"
            placeholder="密码"
            size="large"
            show-password
            @keyup.enter="submitLogin"
          />
          <el-button type="primary" size="large" :loading="loading" @click="submitLogin">
            登录
          </el-button>
          <p v-if="error" class="error">{{ error }}</p>
        </div>
      </el-tab-pane>

      <!-- 注册：工号 + 姓名必填，只会注册成员工，管理员只能由后台创建 -->
      <el-tab-pane label="注册" name="register">
        <div class="form">
          <el-input v-model="regEmployeeNo" placeholder="工号（唯一，登录用）" size="large" />
          <el-input v-model="regName" placeholder="姓名（必填，显示用）" size="large" />
          <el-input
            v-model="regPassword"
            type="password"
            placeholder="密码（至少 6 位）"
            size="large"
            show-password
          />
          <el-input v-model="regPhone" placeholder="手机号（选填）" size="large" />
          <el-input v-model="regEmail" placeholder="邮箱（选填）" size="large" />
          <el-button type="primary" size="large" :loading="regLoading" @click="submitRegister">
            注册并登录
          </el-button>
          <p class="hint">注册后由管理员分配部门；未分配前不能查询业务数据</p>
          <p v-if="regError" class="error">{{ regError }}</p>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.login {
  height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  max-width: 400px;
  margin: 0 auto;
  padding: 0 16px;
}

.login h1 {
  font-size: 24px;
  color: #1f2329;
  margin-bottom: 6px;
}

.subtitle {
  font-size: 13px;
  color: #86909c;
  margin-bottom: 16px;
}

.tabs {
  width: 100%;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 4px;
}

.error {
  color: #f56c6c;
  font-size: 13px;
}

.hint {
  color: #86909c;
  font-size: 12px;
  text-align: center;
}
</style>
