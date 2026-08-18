<script setup>
// 管理后台（Day 14）：只有管理员能看到、能进
// 两个 Tab：文档管理（上传/列表/删除）、用户管理（列表/改角色）
// 所有请求都带 token（后端管理接口都要求 admin，否则 403）
import { ref, computed, onMounted } from 'vue'
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

async function loadDocuments() {
  const res = await fetch('/api/v1/documents', { headers: authHeaders() })
  if (res.ok) docs.value = await res.json()
}

function onUploadSuccess() {
  ElMessage.success('上传成功，正在入库')
  loadDocuments()
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

onMounted(() => {
  loadDocuments()
  loadUsers()
})
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
            accept=".pdf"
          >
            <el-button type="primary">上传 PDF 到知识库</el-button>
          </el-upload>
          <span class="tip">上传即入库（解析 → 切分 → 向量化），员工就能在聊天里搜到</span>
        </div>

        <el-table :data="docs" stripe>
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="filename" label="文件名" min-width="200" />
          <el-table-column prop="chunk_count" label="片段数" width="90" />
          <el-table-column prop="status" label="状态" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'processed' ? 'success' : 'info'">
                {{ row.status }}
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
          <el-table-column prop="department" label="部门" min-width="120">
            <template #default="{ row }">{{ row.department || '未分配' }}</template>
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
          只有超级管理员能改角色，且只能在员工/管理员之间改。超级管理员角色只进不出，由种子脚本维护。
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
</style>
