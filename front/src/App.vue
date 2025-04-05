<!--<template>-->
<!--  <div id="app">-->
<!--    <FileUpload />-->
<!--  </div>-->
<!--</template>-->

<!--<script setup>-->
<!--import FileUpload from './components/FileUpload.vue';-->
<!--</script>-->


<!--<template>-->
<!--  <div>-->
<!--    <PDFViewer pdfUrl="/IDKL.pdf" :scale="1.2" />-->
<!--  </div>-->
<!--</template>-->

<!--<script setup>-->
<!--import PDFViewer from './components/PDFViewer.vue'-->
<!--</script>-->


<template>
  <!-- 路由导航 -->
  <nav>
    <router-link to="/">Home</router-link> |
    <router-link to="/pdfview">About</router-link> |
    <router-link to="/test">test</router-link>
  </nav>

  <!-- 路由出口 -->
  <router-view/>
</template>
<script setup>
</script>