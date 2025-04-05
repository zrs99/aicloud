from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from .serializers import UploadedFileSerializer
import os

from django.http import FileResponse
from pathlib import Path

from .PDFMathTranslate.pdf2zh.high_level import translate, download_remote_fonts
from .PDFMathTranslate.pdf2zh.doclayout import OnnxModel, ModelInstance
from channels.layers import get_channel_layer

import os
from django.http import FileResponse
from pathlib import Path
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import uuid
from celery.result import AsyncResult
from django.http import JsonResponse

from celery import shared_task
from celery.result import AsyncResult
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import time
from .tasks import aipdf


class FileDownloadView(APIView):
    def get(self, request, task_id):
        task = AsyncResult(task_id)
        if task.state != 'SUCCESS':
            return JsonResponse({"error": "任务未完成"}, status=400)

        translated_path = task.result
        print(translated_path)
        response = FileResponse(open(translated_path, 'rb'), content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(translated_path)}"'
        response['Content-Type'] = 'application/octet-stream'  # 通用二进制流类型
        return response


class FileUploadView(APIView):  # APIView 是 DRF 提供的一个基础视图类，用于处理 HTTP 请求
    def post(self, request, *args, **kwargs):
        # 保存上传的文件
        file_serializer = UploadedFileSerializer(data=request.data)
        # print(file_serializer.is_valid())
        if file_serializer.is_valid():
            uploaded_file = file_serializer.save()

            file_path = uploaded_file.file.path  # 获取文件路径和扩展名
            # task_id = str(uuid.uuid4())  # 生成任务 ID

            # 处理文件
            from django.conf import settings
            save_path = Path(settings.BASE_DIR) / 'media' / 'blogs' / 'processed'  # Path 对象: 表示一个文件系统路径
            save_path.mkdir(parents=True, exist_ok=True)  # parents=true自动创建路径中所有缺失的父目录 exist_ok=true当目标目录已存在时不会抛出错误

            # 启动异步任务
            task = aipdf.delay(file_path, str(save_path))
            # task_id.result = file_processed_path
            # 返回任务 ID
            return Response({'task_id': task.id, "message": "翻译任务已启动"}, status=status.HTTP_200_OK)
        else:
            return Response(file_serializer.errors, status=status.HTTP_400_BAD_REQUEST)


