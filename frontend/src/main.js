import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './style.css'
import App from './App.vue'

const app = createApp(App)
app.use(ElementPlus)  // 全量注册组件库（按钮/输入框/标签都能直接用）
app.mount('#app')
