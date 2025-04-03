<template>
  <div class="pdf-viewer-container">
    <div class="pdf-scroll-container" ref="scrollContainer" @scroll="handleScroll">
      <div class="pdf-pages-container" :style="{ height: totalHeight + 'px' }">
        <div
          v-for="page in visiblePages"
          :key="page.pageNumber"
          class="pdf-page-container"
          :style="{
            top: page.offset + 'px',
            height: page.height + 'px',
            width: '100%'
          }"
        >
          <canvas
            :ref="el => setCanvasRef(el, page.pageNumber)"
            :width="page.width"
            :height="page.height"
          ></canvas>
        </div>
      </div>
    </div>
    <div v-if="loading" class="loading-indicator">加载中...</div>
    <div v-if="error" class="error-message">{{ error }}</div>
  </div>
</template>



<script setup>
import { ref, onMounted, onUnmounted, onErrorCaptured } from 'vue'
import * as pdfjsLib from 'pdfjs-dist/build/pdf'
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min?url'

// 配置 PDF.js worker（添加回退逻辑）
try {
  pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker
} catch (err) {
  console.warn('本地Worker加载失败，使用CDN回退')
  pdfjsLib.GlobalWorkerOptions.workerSrc =
    'https://cdn.jsdelivr.net/npm/pdfjs-dist@3.4.120/build/pdf.worker.min.js'
}

const props = defineProps({
  pdfUrl: {
    type: String,
    default: "/IDKL.pdf",
    required: true
  },
  scale: {
    type: Number,
    default: 1.5
  },
  bufferPages: {
    type: Number,
    default: 2
  }
})

// Refs
const scrollContainer = ref(null)
const pageCanvases = ref([])
const renderTasks = new Map()
const pdfDoc = ref(null)
const pageCount = ref(0)
const totalHeight = ref(0)
const pageDimensions = ref([])
const visiblePages = ref([])
const loading = ref(true)
const error = ref(null)
const viewportHeight = ref(0)

// 初始化PDF
const initPDF = async () => {
  try {
    // 验证PDF文件可访问
    const fileExists = await verifyPDFAccess(props.pdfUrl)
    if (!fileExists) throw new Error('PDF文件无法访问')

    // 加载文档
    const loadingTask = pdfjsLib.getDocument({
      url: props.pdfUrl,
      disableAutoFetch: true,
      disableStream: true
    })

    pdfDoc.value = await loadingTask.promise
    pageCount.value = pdfDoc.value.numPages
    pageCanvases.value = new Array(pageCount.value).fill(null)

    // 计算页面尺寸
    await calculatePageDimensions()
    updateVisiblePages()
  } catch (err) {
    console.error('PDF初始化失败:', err)
    error.value = `加载失败: ${err.message}`
  } finally {
    loading.value = false
  }
}

// 验证PDF可访问性
const verifyPDFAccess = async (url) => {
  try {
    const response = await fetch(url, { method: 'HEAD' })
    return response.ok
  } catch {
    return false
  }
}

// 计算页面尺寸
const calculatePageDimensions = async () => {
  const dimensions = []
  let currentOffset = 0

  for (let i = 1; i <= pageCount.value; i++) {
    const page = await pdfDoc.value.getPage(i)
    const viewport = page.getViewport({ scale: props.scale })

    dimensions.push({
      pageNumber: i,
      height: viewport.height,
      width: viewport.width,
      offset: currentOffset
    })

    currentOffset += viewport.height
  }

  pageDimensions.value = dimensions
  totalHeight.value = currentOffset
}

// 设置Canvas引用
const setCanvasRef = (el, pageNumber) => {
  if (el) {
    pageCanvases.value[pageNumber - 1] = el
    // 立即渲染可见页面
    if (visiblePages.value.some(p => p.pageNumber === pageNumber)) {
      renderPage(pageNumber)
    }
  }
}

// 渲染页面
const renderPage = async (pageNumber) => {
  if (!pdfDoc.value || renderTasks.has(pageNumber)) return

  try {
    const page = await pdfDoc.value.getPage(pageNumber)
    const canvas = pageCanvases.value[pageNumber - 1]
    if (!canvas) return

    const dimension = pageDimensions.value[pageNumber - 1]
    const viewport = page.getViewport({ scale: props.scale })

    // 确保Canvas尺寸正确
    canvas.width = dimension.width
    canvas.height = dimension.height

    const task = page.render({
      canvasContext: canvas.getContext('2d'),
      viewport: viewport
    })

    renderTasks.set(pageNumber, task)
    await task.promise
  } catch (err) {
    if (err.name !== 'RenderingCancelledException') {
      console.error(`页面${pageNumber}渲染失败:`, err)
    }
  } finally {
    renderTasks.delete(pageNumber)
  }
}

// 更新可见页面
const updateVisiblePages = () => {
  if (!scrollContainer.value || pageDimensions.value.length === 0) return

  viewportHeight.value = scrollContainer.value.clientHeight
  const scrollTop = scrollContainer.value.scrollTop
  const bufferHeight = viewportHeight.value * props.bufferPages

  const startY = Math.max(0, scrollTop - bufferHeight)
  const endY = scrollTop + viewportHeight.value + bufferHeight

  visiblePages.value = pageDimensions.value.filter(
    page => page.offset + page.height > startY && page.offset < endY
  )

  // 批量渲染可见页面
  visiblePages.value.forEach(page => {
    if (pageCanvases.value[page.pageNumber - 1]) {
      renderPage(page.pageNumber)
    }
  })
}

// 滚动处理
const handleScroll = () => {
  requestAnimationFrame(updateVisiblePages)
}

// 窗口大小变化处理
const handleResize = () => {
  if (pdfDoc.value) {
    calculatePageDimensions().then(updateVisiblePages)
  }
}

// 生命周期
onMounted(() => {
  initPDF()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  renderTasks.forEach(task => task.cancel())
  renderTasks.clear()
  window.removeEventListener('resize', handleResize)

  if (pdfDoc.value) {
    pdfDoc.value.destroy()
    pdfDoc.value = null
  }
})

onErrorCaptured((err) => {
  error.value = `组件错误: ${err.message}`
  return false
})
</script>

<style scoped>
.pdf-viewer-container {
  position: relative;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  background: #f5f5f5;
}

.pdf-scroll-container {
  width: 100%;
  height: 100%;
  overflow-y: auto;
  position: relative;
}

.pdf-pages-container {
  position: relative;
  width: 100%;
}

.pdf-page-container {
  position: absolute;
  width: 100%;
  display: flex;
  justify-content: center;
  padding: 20px 0;
  box-sizing: border-box;
}

.pdf-page-container canvas {
  background: white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  max-width: 100%;
}

.loading-indicator,
.error-message {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  padding: 12px 24px;
  border-radius: 4px;
  font-size: 16px;
}

.loading-indicator {
  background: rgba(0, 0, 0, 0.7);
  color: white;
}

.error-message {
  background: #ffebee;
  color: #c62828;
  border: 1px solid #ef9a9a;
  max-width: 80%;
  text-align: center;
}
</style>
