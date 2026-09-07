<script setup>
// 管理后台（Day 14）：只有管理员能看到、能进
// 两个 Tab：文档管理（上传/列表/删除）、用户管理（列表/改角色）
// 所有请求都带 token（后端管理接口都要求 admin，否则 403）
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const props = defineProps({
  token: { type: String, required: true },
  userRole: { type: String, default: '' },  // Day 15：当前登录者角色，决定角色列能不能改
})

// 角色 → 显示名
function roleLabel(role) {
  return { employee: '员工', admin: '管理员', super_admin: '超级管理员' }[role] || role
}

// 请求头：管理接口都要"我是谁"
function authHeaders() {
  return { Authorization: `Bearer ${props.token}` }
}

// ==================== 文档管理 ====================
const docs = ref([])

// el-upload 的"把 token 带上"：headers 必须是一个对象
const uploadHeaders = computed(() => authHeaders())

// ===== 后台入库轮询（Day 18）=====
// 上传是异步的：接口秒回，入库在后台跑。列表里只要还有"排队中/处理中"，
// 就每 3 秒刷新一次，全到终态（已完成/失败）就停。
let pollTimer = null

function hasPending() {
  return docs.value.some(d => d.status === 'uploading' || d.status === 'processing')
}

async function loadDocuments() {
  const res = await fetch('/api/v1/documents', { headers: authHeaders() })
  if (res.ok) {
    docs.value = await res.json()
    if (hasPending()) startPolling()
    else stopPolling()
  }
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(loadDocuments, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function onUploadSuccess() {
  ElMessage.success('上传成功，后台入库中…')
  loadDocuments() // 拉一次；还有没跑完的，loadDocuments 会自动接着轮询
}

// 状态 → 标签文案和颜色（Day 18：上传变异步后新增 排队/处理中/失败 三种）
function statusInfo(status) {
  return {
    uploading: { label: '排队中', type: 'info' },
    processing: { label: '处理中', type: 'warning' },
    processed: { label: '已完成', type: 'success' },
    failed: { label: '失败', type: 'danger' },
  }[status] || { label: status || '未知', type: 'info' }
}

function onUploadError() {
  ElMessage.error('上传失败')
}

async function deleteDoc(row) {
  try {
    await ElMessageBox.confirm(`确定删除「${row.filename}」吗？向量和文件会一起清掉。`, '删除确认', {
      type: 'warning',
    })
  } catch {
    return // 用户点了取消
  }
  const res = await fetch(`/api/v1/documents/${row.id}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (res.ok) {
    ElMessage.success('已删除')
    loadDocuments()
  } else {
    ElMessage.error('删除失败')
  }
}

// ==================== 用户管理 ====================
const users = ref([])

async function loadUsers() {
  const res = await fetch('/api/v1/users', { headers: authHeaders() })
  if (res.ok) users.value = await res.json()
}

async function changeRole(row, role) {
  const res = await fetch(`/api/v1/users/${row.id}/role`, {
    method: 'PUT',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  })
  if (res.ok) {
    ElMessage.success(`${row.name} → ${role === 'admin' ? '管理员' : '员工'}`)
    loadUsers() // 刷新拿最新角色
  } else {
    const data = await res.json()
    ElMessage.error(data.detail || '修改失败')
    loadUsers() // 失败了也要把下拉框还原
  }
}

async function changeDepartment(row) {
  const department = row.department?.trim() || null
  const res = await fetch(`/api/v1/users/${row.id}/department`, {
    method: 'PUT',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ department }),
  })
  if (res.ok) {
    ElMessage.success(`${row.name} → ${department || '未分配部门'}`)
    loadUsers()
  } else {
    const data = await res.json()
    ElMessage.error(data.detail || '修改失败')
    loadUsers()
  }
}

onMounted(() => {
  loadDocuments()
  loadUsers()
})

onUnmounted(stopPolling) // 离开页面必须停掉轮询，不然定时器泄漏
</script>

<template>
  <div class="panel">
    <el-tabs>
      <!-- 文档管理 -->
      <el-tab-pane label="文档管理">
        <div class="toolbar">
          <el-upload
            :action="'/api/v1/documents/upload'"
            :headers="uploadHeaders"
            :show-file-list="false"
            :on-success="onUploadSuccess"
            :on-error="onUploadError"
            accept=".pdf,.docx,.txt,.md"
          >
            <el-button type="primary">上传文档到知识库</el-button>
          </el-upload>
          <span class="tip">支持 PDF / Word / TXT / Markdown，文档内图表自动识别入库，超大文件后台处理，最大 200MB</span>
        </div>

        <el-table :data="docs" stripe>
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="filename" label="文件名" min-width="200" />
          <el-table-column prop="chunk_count" label="片段数" width="90" />
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <!-- 失败：悬停显示后台入库的报错原因 -->
              <el-tooltip
                v-if="row.status === 'failed'"
                :content="row.error_message || '入库失败'"
                placement="top"
              >
                <el-tag size="small" type="danger">失败</el-tag>
              </el-tooltip>
              <el-tag v-else size="small" :type="statusInfo(row.status).type">
                <span v-if="row.status === 'processing'" class="spinner" />
                {{ statusInfo(row.status).label }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_time" label="上传时间" width="180" />
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button size="small" type="danger" @click="deleteDoc(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 用户管理 -->
      <el-tab-pane label="用户管理">
        <el-table :data="users" stripe>
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="employee_no" label="工号" width="120" />
          <el-table-column prop="name" label="姓名" width="120" />
          <el-table-column prop="department" label="部门" min-width="160">
            <template #default="{ row }">
              <el-input
                v-if="row.role === 'employee'"
                v-model="row.department"
                placeholder="未分配"
                size="small"
                clearable
                @change="changeDepartment(row)"
              />
              <span v-else>{{ row.department || '不限制' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="角色" width="160">
            <template #default="{ row }">
              <!-- Day 15：
                只有超级管理员能改角色，且只能改 employee/admin（不能授予/撤销 super_admin）；
                普通管理员和 super_admin 那行都只显示纯文本 -->
              <el-select
                v-if="props.userRole === 'super_admin' && row.role !== 'super_admin'"
                v-model="row.role"
                size="small"
                @change="(v) => changeRole(row, v)"
              >
                <el-option label="员工" value="employee" />
                <el-option label="管理员" value="admin" />
              </el-select>
              <el-tag
                v-else
                size="small"
                :type="row.role === 'super_admin' ? 'danger' : row.role === 'admin' ? 'warning' : 'info'"
              >
                {{ roleLabel(row.role) }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
        <p class="hint">
          管理员可分配员工部门；只有超级管理员能改角色。超级管理员角色只进不出，由种子脚本维护。
        </p>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.panel {
  flex: 1;
  min-height: 0; /* 允许内部滚动，否则 flex 子项撑破容器 */
  overflow-y: auto;
  padding: 20px 24px;
  background: #fafafa;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 16px;
}

.tip {
  font-size: 12px;
  color: #86909c;
}

.hint {
  font-size: 12px;
  color: #86909c;
  margin-top: 12px;
}

/* 处理中的小转圈（纯 CSS，不引图标库） */
.spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  margin-right: 4px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  vertical-align: -1px;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
