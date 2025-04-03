from django.apps import AppConfig


class BlogsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "blogs"

    def ready(self):
        # 确保任务模块被加载
        from . import tasks  # noqa
        assert tasks.aipdf.name == 'blogs.tasks.aipdf'  # 验证任务名称
