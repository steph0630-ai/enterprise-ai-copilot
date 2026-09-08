<script setup>
// 管理后台：知识库管理、用户管理两个入口
// 所有请求都带 token（后端管理接口都要求 admin，否则 403）
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const props = defineProps({
  token: { type: String, required: true },
  userRole: { type: String, default: '' },  // Day 15：当前登录者角色，决定角色列能不能改
  userDepartment: { type: String, default: '' },
})
const isSuperAdmin = computed(() => props.userRole === 'super_admin')

// 角色 → 显示名
function roleLabel(role) {
  return { employee: '员工', admin: '部门管理员', super_admin: '超级管理员' }[role] || role
}

// 请求头：管理接口都要"我是谁"
function authHeaders() {
  return { Authorization: `Bearer ${props.token}` }
}

// ==================== 文档管理 ====================
const docs = ref([])
const users = ref([])
const knowledgeBases = ref([])
const knowledgeBaseId = ref(null)
const newKnowledgeBase = ref({ name: '', visibility: 'private', department: '' })
const createDialogVisible = ref(false)
const overviewDialogVisible = ref(false)
const memberDialogVisible = ref(false)
const memberKnowledgeBase = ref(null)
const members = ref([])
const newMemberId = ref(null)
const availableMemberUsers = computed(() => users.value.filter(
  user => user.role === 'employee' && !members.value.some(member => member.id === user.id),
))
const selectedKnowledgeBase = computed(() => (
  knowledgeBases.value.find(kb => kb.id === knowledgeBaseId.value) || null
))
const departments = computed(() => [...new Set(
  users.value.map(user => user.department).filter(Boolean),
)])

function visibilityLabel(kb) {
  if (kb.visibility === 'public') return '全员可见'
  if (kb.visibility === 'department') return `${kb.department || '未指定部门'}可见`
  return '指定成员可见'
}

// el-upload 的"把 token 带上"：headers 必须是一个对象
const uploadHeaders = computed(() => authHeaders())
const uploadData = computed(() => ({ knowledge_base_id: knowledgeBaseId.value }))

async function loadKnowledgeBases() {
  const res = await fetch('/api/v1/knowledge-bases', { headers: authHeaders() })
  if (!res.ok) return
  knowledgeBases.value = (await res.json()).filter(kb => kb.can_manage)
  if (!knowledgeBases.value.some(kb => kb.id === knowledgeBaseId.value)) {
    knowledgeBaseId.value = knowledgeBases.value[0]?.id || null
  }
  loadDocuments()
}

async function createKnowledgeBase() {
  const name = newKnowledgeBase.value.name.trim()
  if (!name) return ElMessage.warning('请输入知识库名称')
  const res = await fetch('/api/v1/knowledge-bases', {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name,
      visibility: isSuperAdmin.value ? newKnowledgeBase.value.visibility : 'department',
      department: isSuperAdmin.value && newKnowledgeBase.value.visibility === 'department'
        ? newKnowledgeBase.value.department.trim() || null
        : props.userDepartment || null,
    }),
  })
  if (!res.ok) {
    const data = await res.json()
    return ElMessage.error(data.detail || '创建失败')
  }
  const created = await res.json()
  newKnowledgeBase.value = { name: '', visibility: 'private', department: '' }
  createDialogVisible.value = false
  await loadKnowledgeBases()
  knowledgeBaseId.value = created.id
  await loadDocuments()
  ElMessage.success('知识库已创建')
}

async function saveKnowledgeBase(row) {
  const name = row.name.trim()
  if (!name) return ElMessage.warning('知识库名称不能为空')
  if (row.visibility === 'department' && !row.department?.trim()) {
    return ElMessage.warning('请输入部门名称')
  }
  const res = await fetch(`/api/v1/knowledge-bases/${row.id}`, {
    method: 'PUT',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name,
      visibility: row.visibility,
      department: row.visibility === 'department' ? row.department.trim() : null,
    }),
  })
  if (!res.ok) {
    const data = await res.json()
    await loadKnowledgeBases()
    return ElMessage.error(data.detail || '保存失败')
  }
  Object.assign(row, await res.json())
  ElMessage.success('知识库设置已保存')
}

async function openMembers(row) {
  memberKnowledgeBase.value = row
  newMemberId.value = null
  const res = await fetch(`/api/v1/knowledge-bases/${row.id}/members`, {
    headers: authHeaders(),
  })
  if (!res.ok) return ElMessage.error('加载成员失败')
  members.value = await res.json()
  memberDialogVisible.value = true
}

async function addMember() {
  if (!newMemberId.value) return
  const res = await fetch(`/api/v1/knowledge-bases/${memberKnowledgeBase.value.id}/members`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: newMemberId.value }),
  })
  if (!res.ok) {
    const data = await res.json()
    return ElMessage.error(data.detail || '添加成员失败')
  }
  await openMembers(memberKnowledgeBase.value)
  ElMessage.success('成员已添加')
}

async function removeMember(row) {
  const res = await fetch(
    `/api/v1/knowledge-bases/${memberKnowledgeBase.value.id}/members/${row.id}`,
    { method: 'DELETE', headers: authHeaders() },
  )
  if (!res.ok) return ElMessage.error('移除成员失败')
  members.value = members.value.filter(member => member.id !== row.id)
  ElMessage.success('成员已移除')
}

// ===== 后台入库轮询（Day 18）=====
// 上传是异步的：接口秒回，入库在后台跑。列表里只要还有"排队中/处理中"，
// 就每 3 秒刷新一次，全到终态（已完成/失败）就停。
let pollTimer = null

function hasPending() {
  return docs.value.some(d => d.status === 'uploading' || d.status === 'processing')
}

async function loadDocuments() {
  if (!knowledgeBaseId.value) {
    docs.value = []
    return
  }
  const res = await fetch(`/api/v1/documents?knowledge_base_id=${knowledgeBaseId.value}`, { headers: authHeaders() })
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
  loadKnowledgeBases()
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
    loadKnowledgeBases()
  } else {
    ElMessage.error('删除失败')
  }
}

// ==================== 用户管理 ====================
async function loadUsers() {
  if (!isSuperAdmin.value) return
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
    ElMessage.success(`${row.name} → ${role === 'admin' ? '部门管理员' : '员工'}`)
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
  loadKnowledgeBases()
  loadUsers()
})

onUnmounted(stopPolling) // 离开页面必须停掉轮询，不然定时器泄漏
</script>

<template>
  <div class="panel">
    <el-tabs>
      <el-tab-pane label="知识库管理">
        <div class="page-title">
          <h2>知识库权限设置</h2>
          <div>
            <el-button @click="overviewDialogVisible = true">查看现有知识库</el-button>
            <el-button @click="createDialogVisible = true">＋ 新建知识库</el-button>
          </div>
        </div>

        <section class="step">
          <span class="step-number">1</span>
          <strong>选择已有知识库</strong>
          <el-select
            v-model="knowledgeBaseId"
            filterable
            no-data-text="知识库不存在，请先新建知识库"
            placeholder="搜索或选择知识库"
            class="kb-picker"
            @change="loadDocuments"
          >
            <el-option v-for="kb in knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id" />
          </el-select>
        </section>

        <el-empty
          v-if="!selectedKnowledgeBase"
          description="知识库不存在，请先新建知识库"
        >
          <el-button type="primary" @click="createDialogVisible = true">新建知识库</el-button>
        </el-empty>

        <template v-else>
          <section class="step permission-step">
            <span class="step-number">2</span>
            <strong>设置可见范围</strong>
            <el-radio-group v-if="isSuperAdmin" v-model="selectedKnowledgeBase.visibility">
              <el-radio-button value="private">私有</el-radio-button>
              <el-radio-button value="department">部门可见</el-radio-button>
              <el-radio-button value="public">全员可见</el-radio-button>
            </el-radio-group>
            <el-tag v-else size="large">部门可见</el-tag>
            <el-select
              v-if="isSuperAdmin && selectedKnowledgeBase.visibility === 'department'"
              v-model="selectedKnowledgeBase.department"
              filterable
              allow-create
              placeholder="选择部门"
              style="width: 180px"
            >
              <el-option v-for="department in departments" :key="department" :label="department" :value="department" />
            </el-select>
            <el-tag v-else-if="!isSuperAdmin" size="large" type="info">
              {{ props.userDepartment }}
            </el-tag>
            <el-button
              v-if="isSuperAdmin && selectedKnowledgeBase.visibility === 'private'"
              @click="openMembers(selectedKnowledgeBase)"
            >管理成员</el-button>
            <el-button type="primary" @click="saveKnowledgeBase(selectedKnowledgeBase)">保存设置</el-button>
          </section>

          <div class="permission-summary">
            {{ visibilityLabel(selectedKnowledgeBase) }} · 文档自动继承此权限
          </div>

          <section class="documents-section">
            <div class="section-title">
              <div><span class="step-number">3</span><strong>该知识库中的文档（{{ docs.length }}）</strong></div>
              <el-upload
                action="/api/v1/documents/upload"
                :headers="uploadHeaders"
                :data="uploadData"
                :show-file-list="false"
                :on-success="onUploadSuccess"
                :on-error="onUploadError"
                accept=".pdf,.docx,.txt,.md"
              >
                <el-button type="primary">＋ 添加文档</el-button>
              </el-upload>
            </div>
            <el-table :data="docs" stripe empty-text="该知识库暂无文档">
              <el-table-column prop="filename" label="文档名称" min-width="220" />
              <el-table-column label="处理状态" width="120">
                <template #default="{ row }">
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
              <el-table-column label="可见范围" min-width="160">
                <el-tag size="small">{{ visibilityLabel(selectedKnowledgeBase) }}</el-tag>
              </el-table-column>
              <el-table-column prop="created_time" label="上传时间" width="180" />
              <el-table-column label="操作" width="90">
                <template #default="{ row }">
                  <el-button size="small" type="danger" link @click="deleteDoc(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </section>
        </template>
      </el-tab-pane>

      <el-tab-pane v-if="isSuperAdmin" label="用户管理">
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
                <el-option label="部门管理员" value="admin" />
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
          超级管理员可分配部门和设置部门管理员。超级管理员角色只进不出，由种子脚本维护。
        </p>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="createDialogVisible" title="新建知识库" width="520px">
      <el-form label-width="90px">
        <el-form-item label="知识库名称">
          <el-input v-model="newKnowledgeBase.name" placeholder="请输入知识库名称" />
        </el-form-item>
        <el-form-item v-if="isSuperAdmin" label="可见范围">
          <el-select v-model="newKnowledgeBase.visibility" style="width: 100%">
            <el-option label="私有" value="private" />
            <el-option label="部门可见" value="department" />
            <el-option label="全员可见" value="public" />
          </el-select>
        </el-form-item>
        <el-form-item
          v-if="isSuperAdmin && newKnowledgeBase.visibility === 'department'"
          label="部门"
        >
          <el-select
            v-model="newKnowledgeBase.department"
            filterable
            allow-create
            placeholder="选择部门"
            style="width: 100%"
          >
            <el-option v-for="department in departments" :key="department" :label="department" :value="department" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="!isSuperAdmin" label="所属部门">
          <el-tag>{{ props.userDepartment || '未分配部门' }}</el-tag>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="createKnowledgeBase">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="overviewDialogVisible" title="现有知识库" width="760px">
      <el-table :data="knowledgeBases" stripe empty-text="暂无知识库">
        <el-table-column prop="name" label="知识库名称" min-width="180" />
        <el-table-column label="可见范围" min-width="150">
          <template #default="{ row }">{{ visibilityLabel(row) }}</template>
        </el-table-column>
        <el-table-column prop="department" label="所属部门" min-width="130">
          <template #default="{ row }">{{ row.department || '—' }}</template>
        </el-table-column>
        <el-table-column prop="document_count" label="文档数量" width="100" />
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button
              type="primary"
              link
              @click="knowledgeBaseId = row.id; loadDocuments(); overviewDialogVisible = false"
            >选择</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <el-dialog
      v-model="memberDialogVisible"
      :title="`私有库成员 · ${memberKnowledgeBase?.name || ''}`"
      width="520px"
    >
      <div class="toolbar">
        <el-select v-model="newMemberId" filterable placeholder="选择员工" style="flex: 1">
          <el-option
            v-for="user in availableMemberUsers"
            :key="user.id"
            :label="`${user.name} · ${user.employee_no} · ${user.department || '未分配部门'}`"
            :value="user.id"
          />
        </el-select>
        <el-button type="primary" :disabled="!newMemberId" @click="addMember">添加</el-button>
      </div>
      <el-table :data="members" empty-text="暂无成员">
        <el-table-column prop="employee_no" label="工号" />
        <el-table-column prop="name" label="姓名" />
        <el-table-column prop="department" label="部门" />
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeMember(row)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
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

.page-title,
.section-title,
.step {
  display: flex;
  align-items: center;
}

.page-title {
  justify-content: space-between;
  margin-bottom: 20px;
}

.page-title h2 {
  margin: 0;
}

.step {
  gap: 16px;
  padding: 20px 0;
  border-bottom: 1px solid #ebeef5;
}

.step-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  margin-right: 10px;
  border-radius: 50%;
  color: white;
  background: #409eff;
}

.kb-picker {
  width: min(560px, 60vw);
}

.permission-step {
  flex-wrap: wrap;
}

.permission-summary {
  margin: 16px 0 24px 44px;
  padding: 14px 18px;
  color: #337ecc;
  background: #ecf5ff;
  border: 1px solid #d9ecff;
  border-radius: 4px;
}

.documents-section {
  padding-top: 8px;
}

.section-title {
  justify-content: space-between;
  margin-bottom: 14px;
}

.section-title > div {
  display: flex;
  align-items: center;
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
