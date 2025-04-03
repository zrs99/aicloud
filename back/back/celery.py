import os
from celery import Celery

# 设置默认的 Django 设置模块
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'back.settings')

app = Celery('back')

# 使用 Django 的配置读取 Celery 配置
app.config_from_object('django.conf:settings', namespace='CELERY')

# 自动发现所有 Django 应用中的 tasks.py
# app.autodiscover_tasks()
app.autodiscover_tasks(['blogs'], related_name='tasks')
