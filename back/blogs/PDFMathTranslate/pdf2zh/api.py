from .high_level import translate, download_remote_fonts
from .doclayout import OnnxModel, ModelInstance


def aipdf(files, save_path):
    params = {
        'lang_in': 'en',
        'lang_out': 'zh',
        'service': 'google',
        'thread': 4,
    }

    ModelInstance.value = OnnxModel.load_available()
    (file_mono, file_dual) = translate(files=[files], model=ModelInstance.value, save_path=save_path, **params)[0]

    return file_mono

