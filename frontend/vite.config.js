import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    // 开发代理：浏览器请求 /api/xxx 由 Vite 转发到后端 8000
    // 前端只"看得见"自己的 5173，跨域被代理绕过了（Day 9）
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
