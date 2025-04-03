
from django.db import models

class UploadedFile(models.Model):
    title = models.CharField(max_length=300)
    file = models.FileField(upload_to='blogs/uploads/')  # 文件将存储在 media/uploads/ 目录下
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title