<template>
  <div class="pdf-viewer-container">
    <!-- 文件上传区域 -->
    <div class="upload-section">
      <div class="upload-box">
        <input
          type="file"
          id="leftPdf"
          accept=".pdf"
          @change="handleFileUpload('left', $event)"
          class="file-input"
        >
        <label for="leftPdf" class="upload-label">
          <span v-if="!leftPdfSource">上传左侧PDF</span>
          <span v-else>{{ leftFileName }}</span>
        </label>
      </div>

      <div class="upload-box">
        <input
          type="file"
          id="rightPdf"
          accept=".pdf"
          @change="handleFileUpload('right', $event)"
          class="file-input"
        >
        <label for="rightPdf" class="upload-label">
          <span v-if="!rightPdfSource">上传右侧PDF</span>
          <span v-else>{{ rightFileName }}</span>
        </label>
      </div>
    </div>

    <!-- PDF展示区域 -->
    <div v-if="showPdfViewer" class="pdf-comparison-container">
      <div class="scroll-container" ref="scrollContainer">
        <div class="content-wrapper">
          <!-- 左侧PDF -->
          <div class="pdf-column left-pdf">
            <div v-for="page in visiblePages" :key="'left-'+page">
              <vue-pdf-embed
                :source="leftPdfSource"
                :page="page"
                @rendered="onPageRendered('left', page)"
                ref="leftPdfPages"
              />
            </div>
            <div v-if="loading" class="loading">加载中...</div>
          </div>

          <!-- 右侧PDF -->
          <div class="pdf-column right-pdf">
            <div v-for="page in visiblePages" :key="'right-'+page">
              <vue-pdf-embed
                :source="rightPdfSource"
                :page="page"
                @rendered="onPageRendered('right', page)"
                ref="rightPdfPages"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import VuePdfEmbed from 'vue-pdf-embed'
import { ref, onMounted, onUnmounted } from 'vue'

export default {
  components: {
    VuePdfEmbed
  },
  setup() {
    // PDF源文件
    const leftPdfSource = ref(null)
    const rightPdfSource = ref(null)
    const leftFileName = ref('')
    const rightFileName = ref('')
    const showPdfViewer = ref(false)

    // 页面状态
    const visiblePages = ref([1, 2, 3])
    const loading = ref(false)
    const lastPage = ref(3)
    const totalPages = ref(10)

    // DOM引用
    const scrollContainer = ref(null)
    const leftPdfPages = ref([])
    const rightPdfPages = ref([])

    // 处理文件上传
    const handleFileUpload = (side, event) => {
      const file = event.target.files[0]
      if (!file || file.type !== 'application/pdf') {
        alert('请上传有效的PDF文件')
        return
      }

      const fileUrl = URL.createObjectURL(file)

      if (side === 'left') {
        leftPdfSource.value = fileUrl
        leftFileName.value = file.name
      } else {
        rightPdfSource.value = fileUrl
        rightFileName.value = file.name
      }

      // 当两个文件都上传后显示PDF查看器
      if (leftPdfSource.value && rightPdfSource.value) {
        showPdfViewer.value = true
        // 重置页码
        visiblePages.value = [1, 2, 3]
        lastPage.value = 3
      }
    }

    // 加载更多页面
    const loadMorePages = () => {
      if (loading.value || lastPage.value >= totalPages.value) return

      loading.value = true
      const newPages = []
      const pagesToLoad = Math.min(2, totalPages.value - lastPage.value)

      for (let i = 1; i <= pagesToLoad; i++) {
        newPages.push(lastPage.value + i)
      }

      visiblePages.value = [...visiblePages.value, ...newPages]
      lastPage.value += pagesToLoad
      loading.value = false
    }

    // 滚动处理
    const handleScroll = () => {
      if (!scrollContainer.value) return

      const scrollPos = scrollContainer.value.scrollTop + scrollContainer.value.clientHeight
      const totalHeight = scrollContainer.value.scrollHeight

      if (totalHeight - scrollPos < 500) {
        loadMorePages()
      }
    }

    // 页面渲染回调
    const onPageRendered = (side, page) => {
      console.log(`${side} PDF 第 ${page} 页渲染完成`)

      // 同步两侧页面高度
      if (leftPdfPages.value[page-1] && rightPdfPages.value[page-1]) {
        const leftHeight = leftPdfPages.value[page-1].$el.clientHeight
        const rightHeight = rightPdfPages.value[page-1].$el.clientHeight
        const maxHeight = Math.max(leftHeight, rightHeight)

        leftPdfPages.value[page-1].$el.style.minHeight = `${maxHeight}px`
        rightPdfPages.value[page-1].$el.style.minHeight = `${maxHeight}px`
      }
    }

    onMounted(() => {
      if (scrollContainer.value) {
        scrollContainer.value.addEventListener('scroll', handleScroll)
      }
    })

    onUnmounted(() => {
      if (scrollContainer.value) {
        scrollContainer.value.removeEventListener('scroll', handleScroll)
      }

      // 释放对象URL
      if (leftPdfSource.value) URL.revokeObjectURL(leftPdfSource.value)
      if (rightPdfSource.value) URL.revokeObjectURL(rightPdfSource.value)
    })

    return {
      leftPdfSource,
      rightPdfSource,
      leftFileName,
      rightFileName,
      showPdfViewer,
      visiblePages,
      loading,
      scrollContainer,
      leftPdfPages,
      rightPdfPages,
      handleFileUpload,
      onPageRendered
    }
  }
}
</script>

<style scoped>
.pdf-viewer-container {
  width: 100%;
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.upload-section {
  display: flex;
  justify-content: center;
  gap: 20px;
  padding: 20px;
  background: #f5f5f5;
}

.upload-box {
  position: relative;
  width: 200px;
  height: 100px;
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
  border: 2px dashed #ccc;
  border-radius: 8px;
  background: white;
  transition: all 0.3s;
}

.upload-label:hover {
  border-color: #409eff;
  background: #f0f7ff;
}

.pdf-comparison-container {
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
  padding: 20px;
  box-sizing: border-box;
}

.left-pdf {
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
