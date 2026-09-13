<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  token: { type: String, required: true },
})
const emit = defineEmits(['back', 'saved'])
const profile = ref(null)
const loading = ref(false)
const submitting = ref(false)
const form = reactive({ name: '', email: '', phone: '' })

const roleLabel = (role) => ({
  employee: '员工',
  admin: '部门管理员',
  super_admin: '超级管理员',
}[role] || role || '—')

function formatTime(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

async function loadProfile() {
  loading.value = true
  try {
    const res = await fetch('/api/v1/users/me', {
      headers: { Authorization: `Bearer ${props.token}` },
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '个人资料加载失败')
    profile.value = data
    form.name = data.name || ''
    form.email = data.email || ''
    form.phone = data.phone || ''
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    loading.value = false
  }
}

async function saveProfile() {
  if (!form.name.trim()) return ElMessage.warning('请填写姓名')
  submitting.value = true
  try {
    const res = await fetch('/api/v1/users/me', {
      method: 'PUT',
      headers: {
        Authorization: `Bearer ${props.token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        name: form.name.trim(),
        email: form.email.trim() || null,
        phone: form.phone.trim() || null,
      }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(Array.isArray(data.detail) ? '请检查填写内容' : data.detail || '保存失败')
    profile.value = data
    emit('saved', data)
    ElMessage.success('保存成功')
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    submitting.value = false
  }
}

onMounted(loadProfile)
</script>

<template>
  <main class="profile-page">
    <div class="page-head">
      <el-button text @click="emit('back')">← 返回对话</el-button>
      <h2>个人中心</h2>
    </div>

    <el-card v-loading="loading" shadow="never" class="profile-card">
      <section class="section">
        <h3>基本信息</h3>
        <el-form :model="form" label-width="80px">
          <el-form-item label="姓名">
            <el-input v-model="form.name" maxlength="50" />
          </el-form-item>
          <el-form-item label="邮箱">
            <el-input v-model="form.email" placeholder="选填" />
          </el-form-item>
          <el-form-item label="手机号">
            <el-input v-model="form.phone" maxlength="20" placeholder="选填" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="submitting" @click="saveProfile">保存</el-button>
          </el-form-item>
        </el-form>
      </section>

      <section class="section readonly">
        <h3>账户信息</h3>
        <div class="info-list">
          <div class="info-item"><span>工号</span><b>{{ profile?.employee_no || '—' }}</b></div>
          <div class="info-item"><span>所属部门</span><b>{{ profile?.department || '未分配部门' }}</b></div>
          <div class="info-item"><span>账户角色</span><el-tag size="small">{{ roleLabel(profile?.role) }}</el-tag></div>
          <div class="info-item"><span>注册时间</span><b>{{ formatTime(profile?.created_time) }}</b></div>
        </div>
      </section>
    </el-card>
  </main>
</template>

<style scoped>
.profile-page {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  background: #f5f7fa;
}

.page-head,
.profile-card {
  max-width: 640px;
  margin: 0 auto;
}

.page-head {
  margin-bottom: 16px;
}

.page-head h2 {
  margin-top: 10px;
  color: #303133;
}

.section + .section {
  margin-top: 8px;
  padding-top: 20px;
  border-top: 1px solid #ebeef5;
}

.section h3 {
  margin-bottom: 18px;
  font-size: 15px;
  color: #303133;
}

.info-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.info-item > span:first-child {
  width: 68px;
  flex-shrink: 0;
  color: #909399;
  font-size: 13px;
}

.info-item b {
  color: #303133;
  font-size: 14px;
  font-weight: 400;
}
</style>
