from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from .serializers import UploadedFileSerializer
import os

from django.http import FileResponse
from pathlib import Path


class FileUploadView(APIView):  # APIView 是 DRF 提供的一个基础视图类，用于处理 HTTP 请求
    parser_classes = (MultiPartParser, FormParser)

    # def get(self, request, *args, **kwargs):
    #     form = UploadFileForm()
    #     return render(request, 'blogs/upload.html', {'form': form})

    def post(self, request, *args, **kwargs):
        # 保存上传的文件
        file_serializer = UploadedFileSerializer(data=request.data)
        if file_serializer.is_valid():
            uploaded_file = file_serializer.save()

            # 获取文件路径和扩展名
            file_path = uploaded_file.file.path

            # 处理文件（示例：对文本文件内容转换为大写，其他文件直接返回）
            from .PDFMathTranslate import aipdf
            from django.conf import settings
            save_path = Path(settings.BASE_DIR) / 'media' / 'blogs' / 'processed'  # Path 对象: 表示一个文件系统路径
            save_path.mkdir(parents=True, exist_ok=True)  # parents=true自动创建路径中所有缺失的父目录 exist_ok=true当目标目录已存在时不会抛出错误

            try:
                # file_processed = aipdf.delay(file_path, save_path)
                file_processed = aipdf(file_path, save_path)
            except Exception as e:
                print(f"An error occurred: {e}")

            # 返回处理后的文件给用户
            response = FileResponse(open(file_processed, 'rb'), content_type='application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_processed)}"'
            return response

        else:
            return Response(file_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# class FileUploadView(View):
#     def get(self, request, *args, **kwargs):
#         form = UploadFileForm()
#         return render(request, 'blogs/upload.html', {'form': form})
#
#     def post(self, request, *args, **kwargs):
#         form = UploadFileForm(request.POST, request.FILES)
#         if form.is_valid():
#             # 保存上传的文件
#             uploaded_file = form.save()
#
#             # 获取文件路径和扩展名
#             file_path = uploaded_file.file.path
#             # file_name = uploaded_file.file.name
#             # file_extension = os.path.splitext(file_name)[1].lower()  # 获取文件扩展名
#
#             # 处理文件（示例：对文本文件内容转换为大写，其他文件直接返回）
#             from .PDFMathTranslate import aipdf
#             from django.conf import settings
#
#             try:
#                 save_path = os.path.join(settings.BASE_DIR, 'media', 'blogs', 'processed')
#                 if not os.path.exists(save_path):
#                     os.mkdir(save_path)
#                 file_processed = aipdf(file_path, save_path)
#             except Exception as e:
#                 print(f"An error occurred: {e}")
#
#             # 返回处理后的文件给用户
#             with open(file_processed, 'rb') as f:
#                 response = HttpResponse(f.read(), content_type='application/octet-stream')
#                 response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_processed)}"'
#                 return response
#         else:
#             return render(request, 'blogs/upload.html', {'form': form})
