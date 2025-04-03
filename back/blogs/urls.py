# from django.urls import path
# from .views import PDFMathTranslate
#
# urlpatterns = [
#     path('PDFMathTranslate', PDFMathTranslate.as_view(), name='PDFMathTranslate'),
# ]

from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('upload/', views.FileUploadView.as_view(), name='upload_file'),
    path('download/<str:task_id>/', views.FileDownloadView.as_view(), name='download_translated_file'),
]



