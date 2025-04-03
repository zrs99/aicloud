from .PDFMathTranslate.pdf2zh.high_level import translate, download_remote_fonts
from .PDFMathTranslate.pdf2zh.doclayout import OnnxModel, ModelInstance
from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


@shared_task(bind=True, name='blogs.tasks.aipdf')
def aipdf(self, file_path, save_path):
    # 获取 Channels 层
    channel_layer = get_channel_layer()

    def update_progress(progress):
        async_to_sync(channel_layer.group_send)(
            f'progress_{self.request.id}',
            {
                'type': 'progress_update',
                'progress': progress,
                'task_id': self.request.id  # 添加任务ID用于追踪
            }
        )

    params = {
        'lang_in': 'en',
        'lang_out': 'zh',
        'service': 'google',
        # 'service': 'deepseek',
        'thread': 4,
    }

    try:
        ModelInstance.value = OnnxModel.load_available()
        (file_mono, file_dual) = translate(files=[file_path], model=ModelInstance.value, save_path=save_path,
                                           envs={'DEEPSEEK_API_KEY': 'sk-6f07edb501904443af1a0c14626d314f',
                                                 'DEEPSEEK_MODEL': 'deepseek-chat'},
                                           update_progress=update_progress,
                                           **params)[0]

        # (file_mono, file_dual) = translate(files=[file_path], model=ModelInstance.value, save_path=save_path,
        #                                    update_progress=update_progress, **params)[0]

        # 返回处理后的文件
        return file_mono
    except Exception as e:
        print(f"An error occurred: {e}")
