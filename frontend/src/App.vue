<script setup>
// 组合式 API：<script setup> 里写的变量/函数，模板里直接用（Day 9）
// Day 10：send() 改成流式接收 SSE，Agent 的答案一个字一个字蹦出来
// Day 12：登录才能用——没 token 显示登录页，请求带 Authorization 头，401 回登录页
import { ref, nextTick } from 'vue'
import Login from './components/Login.vue'
import AdminPanel from './components/AdminPanel.vue'  // Day 14：管理后台（只有管理员能进）

// 登录态（存 localStorage，刷新不丢）：
// token 为空 = 未登录，显示登录页
const token = ref(localStorage.getItem('token') || '')
const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))

function onLogin(access_token, userInfo) {
  token.value = access_token
  user.value = userInfo
  localStorage.setItem('token', access_token)
  localStorage.setItem('user', JSON.stringify(userInfo))
}

// 双入口（Day 14）：'chat' 聊天页 / 'admin' 管理后台
// 只有管理员能看到并切到 admin；员工永远停在聊天页
const view = ref('chat')

function logout() {
  token.value = ''
  user.value = null
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  messages.value = []
  conversationId.value = ''
  view.value = 'chat'
}

// 消息列表：{ role: 'user' | 'assistant', content, tools }
const messages = ref([])
const input = ref('')        // 输入框内容（v-model 双向绑定）
const loading = ref(false)   // 等 Agent 回复时禁用按钮，防重复提交
const listRef = ref(null)    // 消息容器 DOM 引用，用于滚动到底部
// 会话 id（Day 11 多轮记忆）：空 = 新会话；后端第一帧 conv 事件会给一个真值
const conversationId = ref('')

async function send() {
  const question = input.value.trim()
  if (!question || loading.value) return  // 空消息 / 正在等，直接忽略

  // 1. 放用户问题 + 一个"空的 Agent 气泡"，流式内容往里填
  messages.value.push({ role: 'user', content: question })
  messages.value.push({ role: 'assistant', content: '', tools: [] })
  input.value = ''
  loading.value = true
  scrollBottom()

  try {
    // 2. 调流式接口（经 Vite 代理转发到后端 8000），带上 token + 会话 id
    const res = await fetch('/api/v1/agent/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token.value}`,  // Day 12：后端靠它认人
      },
      body: JSON.stringify({ query: question, conversation_id: conversationId.value }),
    })
    if (res.status === 401) {
      logout()  // token 过期/无效 → 清掉登录态，回登录页
      return
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`)

    // 3. 逐块读流。fetch 的 body 是 ReadableStream，要用 reader 一帧帧取
    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      // SSE 事件之间用空行(\n\n)分隔，可能一次收到多个，逐个切出来
      let idx
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const raw = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        handleEvent(raw)
      }
    }
  } catch (e) {
    // 4. 请求失败：通常是后端没起 / 代理没配
    handleEvent(`data: ${JSON.stringify({ type: 'error', message: e.message })}\n`)
  } finally {
    loading.value = false
    scrollBottom()
  }
}

// 解析一帧 SSE，按 type 分发
function handleEvent(raw) {
  const line = raw.split('\n').find((l) => l.startsWith('data: '))
  if (!line) return
  let event
  try {
    event = JSON.parse(line.slice('data: '.length))
  } catch {
    return  // 不是合法 JSON 的帧直接忽略
  }

  const last = messages.value[messages.value.length - 1]
  if (event.type === 'conv') {
    conversationId.value = event.conversation_id  // 记下会话 id，下个问题带着它
  } else if (event.type === 'token') {
    last.content += event.content      // 把新吐出来的字拼上去 → 打字机效果
    scrollBottom()
  } else if (event.type === 'tool') {
    if (!last.tools.includes(event.name)) last.tools.push(event.name)  // 亮徽章
    scrollBottom()
  } else if (event.type === 'done') {
    if (!last.content) last.content = '（Agent 没有返回内容）'
    if (event.tools_used && last.tools.length === 0) last.tools = event.tools_used
    scrollBottom()
  } else if (event.type === 'error') {
    last.content = (last.content || '') + `\n[出错] ${event.message}`
    scrollBottom()
  }
}

// 等 DOM 更新完，把滚动条拉到底部让新内容可见
function scrollBottom() {
  nextTick(() => {
    if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
  })
}
</script>

<template>
  <!-- 未登录 → 登录页；已登录 → 聊天界面 -->
  <Login v-if="!token" @login="onLogin" />

  <div v-else class="app">
    <header class="header">
      <div>
        <h1>企业智能助手</h1>
        <p class="subtitle">问知识、查数据——Agent 自动判断并调用工具</p>
      </div>
      <div class="user-box">
        <div class="whoami">
          <span class="user-name">{{ user?.name }}</span>
          <span class="user-no">{{ user?.employee_no }}</span>
        </div>
        <el-tag size="small" :type="user?.role === 'admin' ? 'danger' : 'info'">
          {{ user?.role === 'admin' ? '管理员' : user?.department || '员工' }}
        </el-tag>
        <!-- Day 14 双入口：只有管理员有这个按钮，员工根本看不到 -->
        <el-button
          v-if="user?.role === 'admin'"
          size="small"
          type="primary"
          plain
          @click="view = view === 'admin' ? 'chat' : 'admin'"
        >
          {{ view === 'admin' ? '返回聊天' : '管理后台' }}
        </el-button>
        <el-button size="small" @click="logout">退出</el-button>
      </div>
    </header>

    <template v-if="view === 'chat'">
    <main class="chat">
      <div class="messages" ref="listRef">
        <div v-if="messages.length === 0" class="empty">
          👋 试试问：<br />
          · 报销流程是什么<br />
          · 各部门订单总金额从高到低
        </div>

        <div v-for="(m, i) in messages" :key="i" class="row" :class="m.role">
          <div class="bubble">
            <div class="who">{{ m.role === 'user' ? '我' : 'Agent' }}</div>
            <div class="text">{{ m.content }}</div>
            <div v-if="m.tools && m.tools.length" class="tools">
              <el-tag v-for="t in m.tools" :key="t" size="small" type="success">
                调用了 {{ t }}
              </el-tag>
            </div>
          </div>
        </div>
      </div>

      <footer class="input-bar">
        <el-input
          v-model="input"
          placeholder="输入你的问题，回车发送"
          :disabled="loading"
          @keyup.enter="send"
        />
        <el-button type="primary" :loading="loading" @click="send">发送</el-button>
      </footer>
    </main>
    </template>

    <!-- Day 14：管理员切到管理后台（文档/用户管理） -->
    <AdminPanel v-else :token="token" />
  </div>
</template>

<style scoped>
/* 整页布局：header 固定，消息区撑满剩余空间并可滚动 */
.app {
  height: 100vh;
  display: flex;
  flex-direction: column;
  max-width: 860px;
  margin: 0 auto;
}

.header {
  padding: 20px 24px;
  border-bottom: 1px solid #e5e7eb;
  background: #fff;
  display: flex;              /* Day 12：左右分栏，左边标题右边用户 */
  justify-content: space-between;
  align-items: center;
}

.header h1 {
  font-size: 22px;
  color: #1f2329;
}

.user-box {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 姓名 + 工号竖排：姓名大、工号小 */
.whoami {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  line-height: 1.3;
}

.user-name {
  font-size: 14px;
  color: #1f2329;
}

.user-no {
  font-size: 11px;
  color: #86909c;
}

.subtitle {
  font-size: 13px;
  color: #86909c;
  margin-top: 4px;
}

.chat {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0; /* 允许内部滚动，否则 flex 子项撑破容器 */
}

/* 消息区：可滚动 */
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.empty {
  text-align: center;
  color: #86909c;
  font-size: 14px;
  line-height: 2;
  margin: auto;
}

.row {
  display: flex;
}

/* 用户消息右对齐，Agent 消息左对齐 */
.row.user {
  justify-content: flex-end;
}

.bubble {
  max-width: 78%;
  background: #fff;
  border-radius: 12px;
  padding: 12px 14px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

.row.user .bubble {
  background: #e8f3ff;
}

.who {
  font-size: 12px;
  color: #86909c;
  margin-bottom: 6px;
}

.text {
  font-size: 15px;
  line-height: 1.7;
  color: #1f2329;
  white-space: pre-wrap; /* 保留模型答案里的换行 */
  word-break: break-word;
}

.tools {
  margin-top: 8px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

/* 底部输入栏 */
.input-bar {
  display: flex;
  gap: 10px;
  padding: 14px 24px;
  border-top: 1px solid #e5e7eb;
  background: #fff;
}

.input-bar .el-input {
  flex: 1;
}
</style>
