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
    # path('upload/success/', views.upload_success.as_view(), name='upload_success'),
]



