// src/router/index.js
import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/components/FileUpload.vue')
  },
  {
    path: '/pdfview',
    name: 'pdfview',
    component: () => import('@/components/PDFViewer.vue')
  },
  {
    path: '/test',
    name: 'test',
    component: () => import('@/components/TestView.vue')
  }
]

const router = createRouter({
  history: createWebHistory(process.env.BASE_URL),
  routes
})

export default router
