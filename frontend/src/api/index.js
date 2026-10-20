import axios from 'axios'
import i18n from '../i18n'
import { setLocaleHeader } from './localeHeader.js'

// 创建axios实例
const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001',
  timeout: 300000, // 5分钟超时（本体生成可能需要较长时间）
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
service.interceptors.request.use(
  config => {
    return setLocaleHeader(config, () => i18n.global.locale.value)
  },
  error => {
    console.error('Request error:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器（容错重试机制）
service.interceptors.response.use(
  response => {
    const res = response.data
    
    // 如果返回的状态码不是success，则抛出错误
    if (!res.success && res.success !== undefined) {
      // Une ressource optionnelle (404 = « absent », pas « cassé ») peut
      // demander le silence : le journal doit rester un signal, pas du bruit
      // (Story 013-5, AC6).
      if (!response.config?.suppressErrorLog) {
        console.error('API Error:', res.error || res.message || 'Unknown error')
      }
      return Promise.reject(new Error(res.error || res.message || 'Error'))
    }
    
    return res
  },
  error => {
    const apiError = error.response?.data?.error || error.response?.data?.message

    if (!error.config?.suppressErrorLog) {
      console.error('Response error:', error)
    }
    
    // 处理超时
    if (error.code === 'ECONNABORTED' && error.message.includes('timeout')) {
      console.error('Request timeout')
    }
    
    // 处理网络错误
    if (error.message === 'Network Error') {
      console.error('Network error - please check your connection')
    }

    // Axios rejects non-2xx responses before the success interceptor can
    // surface the backend's safe, actionable error message.
    if (typeof apiError === 'string' && apiError) {
      error.message = apiError
    }
    
    return Promise.reject(error)
  }
)

export default service
