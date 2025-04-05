<template>
  <div class="pdf-comparison-container">
    <!-- 上传和翻译控制区域 -->
    <div class="control-panel">
      <div class="upload-section">
        <div class="upload-box">
          <input
            type="file"
            id="originalPdf"
            accept=".pdf"
            @change="handleFileUpload"
            class="file-input"
          >
          <label for="originalPdf" class="upload-label">
            <span v-if="!originalFileName">上传PDF文件</span>
            <span v-else>{{ originalFileName }}</span>
          </label>
        </div>

        <div class="language-selector">
          <label>目标语言:</label>
          <select v-model="selectedLanguage" class="language-dropdown">
            <option value="zh">中文(简体)</option>
            <option value="en">英语</option>
          </select>
          <button
            @click="uploadAndTranslate"
            class="action-button"
            :disabled="!originalPdfSource"
          >
            翻译文档
          </button>
        </div>
      </div>

      <p v-if="message" class="message">{{ message }}</p>

      <div class="progress-section" v-if="progress > 0">
        <div class="progress-container">
          <label>翻译进度:</label>
          <progress :value="progress" max="100" class="progress-bar"></progress>
          <span class="progress-text">{{ progress }}%</span>
        </div>
        <button
          v-if="translationComplete"
          @click="loadTranslatedPdf"
          class="action-button"
        >
          加载翻译结果
        </button>
      </div>
    </div>

    <!-- PDF对比展示区域 -->
    <div v-if="showPdfViewer" class="pdf-viewer-wrapper">
      <div class="scroll-container" ref="scrollContainer">
        <div class="content-wrapper">
          <!-- 左侧原始PDF -->
          <div class="pdf-column original-pdf">
            <div class="pdf-header">原始文档 (共{{ originalTotalPages }}页)</div>
            <div v-for="page in originalVisiblePages" :key="'original-'+page">
              <vue-pdf-embed
                :source="originalPdfSource"
                :page="page"
                @rendered="onPageRendered('original', page)"
                ref="originalPdfPages"
              />
            </div>
          </div>

          <!-- 右侧翻译后PDF -->
          <div class="pdf-column translated-pdf">
            <div class="pdf-header">翻译结果 (共{{ translatedTotalPages }}页)</div>
            <div v-for="page in translatedVisiblePages" :key="'translated-'+page">
              <vue-pdf-embed
                :source="translatedPdfSource"
                :page="page"
                @rendered="onPageRendered('translated', page)"
                ref="translatedPdfPages"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import VuePdfEmbed from 'vue-pdf-embed'
import axios from 'axios'
// import * as pdfjsLib from 'pdfjs-dist'
// import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.entry'

// 配置pdf.js worker路径
// pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker

// 文件上传相关
const originalPdfSource = ref(null)
const originalFileName = ref('')
const selectedLanguage = ref('zh')

// 翻译相关
const translatedPdfSource = ref(null)
const progress = ref(0)
const translationComplete = ref(false)
const taskId = ref(null)
let ws = null

// PDF展示相关
const showPdfViewer = ref(false)
const originalVisiblePages = ref([])
const translatedVisiblePages = ref([])
const originalTotalPages = ref(0)
const translatedTotalPages = ref(0)

// DOM引用
const scrollContainer = ref(null)
const originalPdfPages = ref([])
const translatedPdfPages = ref([])
const message = ref('')

// 处理文件上传
const handleFileUpload = async (event) => {
  const file = event.target.files[0]
  if (!file || file.type !== 'application/pdf') {
    alert('请上传有效的PDF文件')
    return
  }

  originalFileName.value = file.name
  originalPdfSource.value = URL.createObjectURL(file)
  translatedPdfSource.value = null
  showPdfViewer.value = false
  progress.value = 0
  translationComplete.value = false

  try {
    // 使用pdfjsLib获取PDF页数
    const loadingTask = pdfjsLib.getDocument({
      url: originalPdfSource.value,
      cMapUrl: 'https://cdn.jsdelivr.net/npm/pdfjs-dist@2.16.105/cmaps/',
      cMapPacked: true
    })
    const pdf = await loadingTask.promise
    originalTotalPages.value = pdf.numPages
    originalVisiblePages.value = Array.from({ length: pdf.numPages }, (_, i) => i + 1)
    showPdfViewer.value = true
  } catch (error) {
    console.error('获取PDF页数失败:', error)
    // 默认显示前10页作为fallback
    originalTotalPages.value = 10
    originalVisiblePages.value = Array.from({ length: 10 }, (_, i) => i + 1)
    showPdfViewer.value = true
  }
}

// 上传并翻译文件
const uploadAndTranslate = async () => {
  if (!originalPdfSource.value) return

  try {
    const fileInput = document.getElementById('originalPdf')
    const file = fileInput.files[0]

    const formData = new FormData()
    formData.append('file', file)
    formData.append('language', selectedLanguage.value)
    formData.append('title', file.name)

    message.value = '翻译排队中'
    const response = await axios.post('http://10.241.109.58:8000/blogs/upload/', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })

    taskId.value = response.data.task_id

    // 建立WebSocket连接监听进度
    ws = new WebSocket(`ws://10.241.109.58:8000/ws/progress/${taskId.value}/`)

    ws.onopen = () => {
      console.log('WebSocket连接已建立')
      ws.send(JSON.stringify({type: 'init', task_id: taskId.value}))
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.progress !== undefined) {
        message.value = ''
        progress.value = data.progress
        if (data.progress >= 100) {
          translationComplete.value = true
        }
      }
    }

    ws.onerror = (error) => {
      console.error('WebSocket错误:', error)
    }

    ws.onclose = () => {
      console.log('WebSocket连接已关闭')
    }

  } catch (error) {
    console.error('文件上传或翻译失败:', error)
  }
}

// 加载翻译后的PDF
const loadTranslatedPdf = async () => {
  if (!taskId.value) return

  try {
    const url = `http://10.241.109.58:8000/blogs/download/${taskId.value}/?t=${Date.now()}`
    translatedPdfSource.value = url

    // 使用pdfjsLib获取翻译后PDF的页数
    const loadingTask = pdfjsLib.getDocument({
      url: translatedPdfSource.value,
      cMapUrl: 'https://cdn.jsdelivr.net/npm/pdfjs-dist@2.16.105/cmaps/',
      cMapPacked: true
    })
    const pdf = await loadingTask.promise
    translatedTotalPages.value = pdf.numPages
    translatedVisiblePages.value = Array.from({ length: pdf.numPages }, (_, i) => i + 1)

    showPdfViewer.value = true
  } catch (error) {
    console.error('加载翻译结果失败:', error)
    // 默认显示前10页作为fallback
    translatedTotalPages.value = 10
    translatedVisiblePages.value = Array.from({ length: 10 }, (_, i) => i + 1)
    showPdfViewer.value = true
  }
}

// 页面渲染回调
const onPageRendered = (type, page) => {
  console.log(`${type} PDF 第 ${page} 页渲染完成`)

  // 同步两侧页面高度
  if (originalPdfPages.value[page-1] && translatedPdfPages.value[page-1]) {
    const originalHeight = originalPdfPages.value[page-1].$el.clientHeight
    const translatedHeight = translatedPdfPages.value[page-1].$el.clientHeight
    const maxHeight = Math.max(originalHeight, translatedHeight)

    originalPdfPages.value[page-1].$el.style.minHeight = `${maxHeight}px`
    translatedPdfPages.value[page-1].$el.style.minHeight = `${maxHeight}px`
  }
}

onMounted(() => {
  if (scrollContainer.value) {
    scrollContainer.value.addEventListener('scroll', () => {
      // 可以在这里添加滚动事件处理
    })
  }
})

onUnmounted(() => {
  if (scrollContainer.value) {
    scrollContainer.value.removeEventListener('scroll', () => {})
  }

  // 释放对象URL
  if (originalPdfSource.value) URL.revokeObjectURL(originalPdfSource.value)
  if (ws) ws.close()
})
</script>


<style scoped>
/* 样式保持不变 */
.pdf-comparison-container {
  width: 100%;
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.control-panel {
  padding: 20px;
  background: #f5f5f5;
  border-bottom: 1px solid #ddd;
}

.upload-section {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 15px;
}

.upload-box {
  position: relative;
  width: 200px;
  height: 40px;
}

.file-input {
  opacity: 0;
  position: absolute;
  width: 100%;
  height: 100%;
  cursor: pointer;
}

.upload-label {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
  border: 1px dashed #ccc;
  border-radius: 4px;
  background: white;
  transition: all 0.3s;
}

.upload-label:hover {
  border-color: #409eff;
  background: #f0f7ff;
}

.language-selector {
  display: flex;
  align-items: center;
  gap: 10px;
}

.language-dropdown {
  padding: 5px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.action-button {
  padding: 8px 16px;
  background-color: #4CAF50;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s;
}

.action-button:hover {
  background-color: #45a049;
}

.action-button:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
}

.progress-section {
  margin-top: 15px;
}

.progress-container {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.progress-bar {
  flex: 1;
  height: 10px;
}

.progress-text {
  min-width: 40px;
  text-align: right;
}

.pdf-viewer-wrapper {
  flex: 1;
  width: 100%;
  overflow: hidden;
}

.scroll-container {
  width: 100%;
  height: 100%;
  overflow-y: auto;
}

.content-wrapper {
  display: flex;
  min-height: 100%;
}

.pdf-column {
  flex: 1;
  padding: 15px;
  box-sizing: border-box;
}

.pdf-header {
  font-weight: bold;
  margin-bottom: 15px;
  padding-bottom: 5px;
  border-bottom: 1px solid #eee;
}

.original-pdf {
  border-right: 1px solid #ddd;
}

.vue-pdf-embed {
  margin-bottom: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.loading {
  text-align: center;
  padding: 20px;
  color: #666;
  background: #f5f5f5;
  margin-top: 10px;
  border-radius: 4px;
}
</style>
