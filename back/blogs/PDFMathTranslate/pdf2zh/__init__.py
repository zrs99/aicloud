import logging
from .high_level import translate, translate_stream

log = logging.getLogger(__name__)

__version__ = "1.9.4"
__all__ = ["translate", "translate_stream"]
__author__ = "Byaidu"
