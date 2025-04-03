<template>
  <div class="upload-container">
    <h1 class="title">文献上传与翻译</h1>

    <!-- 语言选择 -->
    <div class="language-selector">
      <label>目标语言:</label>
      <select v-model="selectedLanguage" class="language-dropdown">
        <option value="zh">中文(简体)</option>
        <option value="en">英语</option>
      </select>
    </div>

    <!-- 文件上传区域 -->
    <div class="upload-area">
      <input type="file" @change="handleFileChange" class="file-input"/>
      <button @click="uploadFile" class="upload-button">上传并翻译</button>
    </div>

    <!-- 进度条 -->
    <div v-if="progress > 0" class="progress-container">
      <label>翻译进度:</label>
      <progress :value="progress" max="100" class="progress-bar"></progress>
      <span class="progress-text">{{ progress }}%</span>
    </div>

    <!-- 接收翻译文件选项 -->
    <div v-if="translationComplete" class="download-option">
      <label>
        <input type="checkbox" v-model="receiveTranslatedFile"/>
        接收翻译后的文件
      </label>
      <button v-if="receiveTranslatedFile" @click="downloadTranslatedFile" class="download-button">
        下载翻译文件
      </button>
    </div>

    <!-- 消息提示 -->
    <p v-if="message" class="message">{{ message }}</p>
  </div>
</template>

<script setup>
import {ref} from 'vue';
import axios from 'axios';

// 响应式数据
const file = ref(null);
const message = ref('');
const progress = ref(0);
const selectedLanguage = ref('zh'); // 默认选择中文
const translationComplete = ref(false);
const receiveTranslatedFile = ref(false);
const taskId = ref(null);
let ws = null;

// 处理文件选择
const handleFileChange = (event) => {
  file.value = event.target.files[0];
  message.value = ''; // 清空消息
};


// 上传文件并翻译
const uploadFile = async () => {
  if (!file.value) {
    message.value = '请选择一个文件';
    return;
  }

  const formData = new FormData();
  formData.append('file', file.value);
  formData.append('language', selectedLanguage.value);
  formData.append('title', file.value.name);

  try {
    message.value = '正在上传并翻译...';


    // const response = await axios.post('http://127.0.0.1:8000/blogs/upload/', formData, {
    const response = await axios.post('http://10.241.109.58:8000/blogs/upload/', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });

    taskId.value = response.data.task_id;

    message.value = '翻译任务已启动！';
    // socket.value = new WebSocket(`ws://127.0.0.1:8000/ws/progress/${taskId}/`);

    ws = new WebSocket(`ws://10.241.109.58:8000/ws/progress/${taskId.value}/`);
    // ws = new WebSocket(`ws://127.0.0.1:8000/ws/progress/${taskId.value}/`);



    ws.onopen = () => {
      console.log('WebSocket 连接已建立');
      // 发送初始化消息
      ws.send(JSON.stringify({type: 'init', task_id: taskId.value}));
    };

    ws.onerror = (error) => {
      console.error('WebSocket 错误:', error);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.progress !== undefined) {
          progress.value = data.progress;
          if (data.progress >= 100) {
            translationComplete.value = true;
          }
        }
      } catch (e) {
        console.error('解析消息失败:', e);
      }
    };

    ws.onclose = () => {
      console.log('WebSocket 连接已关闭');
    };

  } catch (error) {
    message.value = '文件上传或翻译失败';
    console.error('Error uploading file:', error);
    progress.value = 0;
    translationComplete.value = false;
  }
};

// 下载翻译文件
const downloadTranslatedFile = async () => {
  // if (!taskId.value) return;
  //
  // try {
  //   const response = await axios.get(`http://localhost:8000/blogs/download/${taskId.value}/`, {
  //     headers: {
  //       'Content-Type': 'multipart/form-data',
  //     },
  //     responseType: 'blob',
  //   });
  //
  //   const url = window.URL.createObjectURL(new Blob([response.data]));
  //   const link = document.createElement('a');
  //   link.href = url;
  //   link.setAttribute('download', `translated_${file.value.name}`);
  //   document.body.appendChild(link);
  //   link.click();
  //   document.body.removeChild(link);
  //
  // } catch (error) {
  //   message.value = '文件下载失败';
  //   console.error('Error downloading file:', error);
  // }

   if (!taskId.value) return;

  try {
    // 添加时间戳防止缓存
    // const url = `http://localhost:8000/blogs/download/${taskId.value}/?t=${Date.now()}`;
    const url = `http://10.241.109.58:8000/blogs/download/${taskId.value}/?t=${Date.now()}`;

    // 方法A：直接创建隐藏链接
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `translated_${file.value.name}`);
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    // // 方法B：使用fetch替代axios
    // const response = await fetch(url);
    // if (!response.ok) throw new Error('Download failed');
    // const blob = await response.blob();
    // const blobUrl = window.URL.createObjectURL(blob);
    // const tempLink = document.createElement('a');
    // tempLink.href = blobUrl;
    // tempLink.setAttribute('download', `translated_${file.value.name}`);
    // tempLink.click();
    // window.URL.revokeObjectURL(blobUrl);

  } catch (error) {
    message.value = '文件下载失败';
    console.error('下载错误:', error);
  }
};

</script>

<style scoped>
.upload-container {
  max-width: 600px;
  margin: 20px auto;
  padding: 20px;
  background-color: #f9f9f9;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.title {
  text-align: center;
  color: #333;
  margin-bottom: 20px;
}

.language-selector {
  margin-bottom: 20px;
}

.language-dropdown {
  padding: 8px;
  font-size: 16px;
  border: 1px solid #ddd;
  border-radius: 4px;
  width: 100%;
  max-width: 200px;
}

.upload-area {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.file-input {
  flex: 1;
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.upload-button {
  padding: 10px 20px;
  background-color: #4CAF50;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.upload-button:hover {
  background-color: #45a049;
}

.progress-container {
  margin-bottom: 20px;
}

.progress-bar {
  width: 100%;
  height: 20px;
}

.progress-text {
  display: block;
  text-align: center;
  margin-top: 5px;
}

.download-option {
  margin-bottom: 20px;
}

.download-button {
  margin-left: 10px;
  padding: 8px 16px;
  background-color: #2196F3;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.download-button:hover {
  background-color: #1976D2;
}

.message {
  text-align: center;
  color: #d32f2f;
  font-weight: bold;
}
</style>