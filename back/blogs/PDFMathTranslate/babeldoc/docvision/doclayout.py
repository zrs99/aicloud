import abc
import ast
import logging
import platform
from collections.abc import Generator

import cv2
import numpy as np
import onnx
import onnxruntime
import pymupdf

import babeldoc.document_il.il_version_1
from babeldoc.assets.assets import get_doclayout_onnx_model_path

# from huggingface_hub import hf_hub_download

logger = logging.getLogger(__name__)


class YoloResult:
    """Helper class to store detection results from ONNX model."""

    def __init__(self, names, boxes=None, boxes_data=None):
        if boxes is not None:
            self.boxes = boxes
        else:
            assert boxes_data is not None
            self.boxes = [YoloBox(data=d) for d in boxes_data]
        self.boxes.sort(key=lambda x: x.conf, reverse=True)
        self.names = names


class DocLayoutModel(abc.ABC):
    @staticmethod
    def load_onnx():
        logger.info("Loading ONNX model...")
        model = OnnxModel.from_pretrained()
        return model

    @staticmethod
    def load_available():
        return DocLayoutModel.load_onnx()

    @property
    @abc.abstractmethod
    def stride(self) -> int:
        """Stride of the model input."""

    @abc.abstractmethod
    def predict(self, image: bytes, imgsz: int = 1024, **kwargs) -> list[int]:
        """
        Predict the layout of a document page.

        Args:
            image: The image of the document page.
            imgsz: Resize the image to this size. Must be a multiple of the stride.
            **kwargs: Additional arguments.
        """

    @abc.abstractmethod
    def handle_document(
        self,
        pages: list[babeldoc.document_il.il_version_1.Page],
        mupdf_doc: pymupdf.Document,
        translate_config,
        save_debug_image,
    ) -> Generator[
        tuple[babeldoc.document_il.il_version_1.Page, YoloResult], None, None
    ]:
        """
        Handle a document.
        """


class YoloBox:
    """Helper class to store detection results from ONNX model."""

    def __init__(self, data=None, xyxy=None, conf=None, cls=None):
        if data is not None:
            self.xyxy = data[:4]
            self.conf = data[-2]
            self.cls = data[-1]
            return
        assert xyxy is not None and conf is not None and cls is not None
        self.xyxy = xyxy
        self.conf = conf
        self.cls = cls


# 检测操作系统类型
os_name = platform.system()

providers = []

if os_name == "Darwin" and False:  # Temporarily disable CoreML due to some issues
    providers.append(
        (
            "CoreMLExecutionProvider",
            {
                "ModelFormat": "MLProgram",
                "MLComputeUnits": "ALL",
                "RequireStaticInputShapes": "0",
                "EnableOnSubgraphs": "0",
            },
        ),
    )
    # workaround for CoreML batch inference issues
    max_batch_size = 1
else:
    max_batch_size = 1
providers.append("CPUExecutionProvider")  # CPU 执行提供者作为通用后备选项


class OnnxModel(DocLayoutModel):
    def __init__(self, model_path: str):
        self.model_path = model_path

        model = onnx.load(model_path)
        metadata = {d.key: d.value for d in model.metadata_props}
        self._stride = ast.literal_eval(metadata["stride"])
        self._names = ast.literal_eval(metadata["names"])

        self.model = onnxruntime.InferenceSession(
            model.SerializeToString(),
            providers=providers,
        )

    @staticmethod
    def from_pretrained():
        pth = get_doclayout_onnx_model_path()
        return OnnxModel(pth)

    @property
    def stride(self):
        return self._stride

    def resize_and_pad_image(self, image, new_shape):
        """
        Resize and pad the image to the specified size, ensuring dimensions are multiples of stride.

        Parameters:
        - image: Input image
        - new_shape: Target size (integer or (height, width) tuple)
        - stride: Padding alignment stride, default 32

        Returns:
        - Processed image
        """
        if isinstance(new_shape, int):
            new_shape = (new_shape, new_shape)

        h, w = image.shape[:2]
        new_h, new_w = new_shape

        # Calculate scaling ratio
        r = min(new_h / h, new_w / w)
        resized_h, resized_w = int(round(h * r)), int(round(w * r))

        # Resize image
        image = cv2.resize(
            image,
            (resized_w, resized_h),
            interpolation=cv2.INTER_LINEAR,
        )

        # Calculate padding size and align to stride multiple
        pad_w = (new_w - resized_w) % self.stride
        pad_h = (new_h - resized_h) % self.stride
        top, bottom = pad_h // 2, pad_h - pad_h // 2
        left, right = pad_w // 2, pad_w - pad_w // 2

        # Add padding
        image = cv2.copyMakeBorder(
            image,
            top,
            bottom,
            left,
            right,
            cv2.BORDER_CONSTANT,
            value=(114, 114, 114),
        )

        return image

    def scale_boxes(self, img1_shape, boxes, img0_shape):
        """
        Rescales bounding boxes (in the format of xyxy by default) from the shape of the image they were originally
        specified in (img1_shape) to the shape of a different image (img0_shape).

        Args:
            img1_shape (tuple): The shape of the image that the bounding boxes are for,
                in the format of (height, width).
            boxes (torch.Tensor): the bounding boxes of the objects in the image, in the format of (x1, y1, x2, y2)
            img0_shape (tuple): the shape of the target image, in the format of (height, width).

        Returns:
            boxes (torch.Tensor): The scaled bounding boxes, in the format of (x1, y1, x2, y2)
        """

        # Calculate scaling ratio
        gain = min(img1_shape[0] / img0_shape[0], img1_shape[1] / img0_shape[1])

        # Calculate padding size
        pad_x = round((img1_shape[1] - img0_shape[1] * gain) / 2 - 0.1)
        pad_y = round((img1_shape[0] - img0_shape[0] * gain) / 2 - 0.1)

        # Remove padding and scale boxes
        boxes[..., :4] = (boxes[..., :4] - [pad_x, pad_y, pad_x, pad_y]) / gain
        return boxes

    def predict(self, image, imgsz=800, batch_size=16, **kwargs):
        """
        Predict the layout of document pages.

        Args:
            image: A single image or a list of images of document pages.
            imgsz: Resize the image to this size. Must be a multiple of the stride.
            batch_size: Number of images to process in one batch.
            **kwargs: Additional arguments.

        Returns:
            A list of YoloResult objects, one for each input image.
        """
        # Handle single image input
        if isinstance(image, np.ndarray) and len(image.shape) == 3:
            image = [image]

        total_images = len(image)
        results = []
        batch_size = min(batch_size, max_batch_size)

        # Process images in batches
        for i in range(0, total_images, batch_size):
            batch_images = image[i : i + batch_size]
            batch_size_actual = len(batch_images)

            # Calculate target size based on the maximum height in the batch
            max_height = max(img.shape[0] for img in batch_images)
            target_imgsz = int(max_height / 32) * 32

            # Preprocess batch
            processed_batch = []
            orig_shapes = []
            for img in batch_images:
                orig_h, orig_w = img.shape[:2]
                orig_shapes.append((orig_h, orig_w))

                pix = self.resize_and_pad_image(img, new_shape=target_imgsz)
                pix = np.transpose(pix, (2, 0, 1))  # CHW
                pix = pix.astype(np.float32) / 255.0  # Normalize to [0, 1]
                processed_batch.append(pix)

            # Stack batch
            batch_input = np.stack(processed_batch, axis=0)  # BCHW
            new_h, new_w = batch_input.shape[2:]

            # Run inference
            batch_preds = self.model.run(None, {"images": batch_input})[0]

            # Process each prediction in the batch
            for j in range(batch_size_actual):
                preds = batch_preds[j]
                preds = preds[preds[..., 4] > 0.25]
                if len(preds) > 0:
                    preds[..., :4] = self.scale_boxes(
                        (new_h, new_w),
                        preds[..., :4],
                        orig_shapes[j],
                    )
                results.append(YoloResult(boxes_data=preds, names=self._names))

        return results

    def handle_document(
        self,
        pages: list[babeldoc.document_il.il_version_1.Page],
        mupdf_doc: pymupdf.Document,
        translate_config,
        save_debug_image,
    ) -> Generator[
        tuple[babeldoc.document_il.il_version_1.Page, YoloResult], None, None
    ]:
        for page in pages:
            translate_config.raise_if_cancelled()
            pix = mupdf_doc[page.page_number].get_pixmap(dpi=72)
            image = np.fromstring(pix.samples, np.uint8).reshape(
                pix.height,
                pix.width,
                3,
            )[:, :, ::-1]
            predict_result = self.predict(image)[0]
            save_debug_image(
                image,
                predict_result,
                page.page_number + 1,
            )
            yield page, predict_result
