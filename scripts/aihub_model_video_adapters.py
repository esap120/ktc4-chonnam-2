"""Original AI Hub model adapters; no application pipeline dependencies."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Protocol

import cv2
import numpy as np
import torch
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict
from typing_extensions import assert_never


class Detection(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    score: float
    bbox_xyxy: tuple[float, float, float, float]
    mask_area_ratio: float | None = None
    mask_rle: str | None = None
    mask_size: tuple[int, int] | None = None


class Detector(Protocol):
    names: tuple[str, ...]

    def predict(self, image: NDArray[np.uint8]) -> tuple[Detection, ...]: ...


class YoloDetector:
    """Use the checkpoint's EMA when present, and the original v7.0 decoder/NMS."""

    def __init__(self, weight: Path, source: Path, confidence: float) -> None:
        sys.path.insert(0, str(source.resolve()))
        from utils.augmentations import letterbox
        from utils.general import non_max_suppression, scale_boxes

        self.letterbox = letterbox
        self.nms = non_max_suppression
        self.scale_boxes = scale_boxes
        checkpoint = torch.load(weight, map_location="cpu", weights_only=False)
        model = (
            checkpoint["ema"]
            if checkpoint.get("ema") is not None
            else checkpoint["model"]
        )
        self.model = model.float().to("cuda").eval()
        self.names = tuple(model.names[i] for i in range(len(model.names)))
        self.confidence = confidence
        self.stride = int(model.stride.max())

    def predict(self, image: NDArray[np.uint8]) -> tuple[Detection, ...]:
        padded = self.letterbox(image, 640, stride=self.stride, auto=True)[0]
        rgb = np.ascontiguousarray(padded.transpose(2, 0, 1)[::-1])
        batch = torch.from_numpy(rgb).to("cuda").float().unsqueeze(0) / 255.0
        with torch.inference_mode():
            pred = self.model(batch)[0]
            boxes = self.nms(pred, self.confidence, 0.45)[0]
            boxes[:, :4] = self.scale_boxes(
                batch.shape[2:], boxes[:, :4], image.shape
            ).round()
        return tuple(
            Detection(
                name=self.names[int(cls)],
                score=float(score),
                bbox_xyxy=(float(x1), float(y1), float(x2), float(y2)),
            )
            for x1, y1, x2, y2, score, cls in boxes.cpu().tolist()
        )


class MaskDetector:
    """Strict-load the original Detectron2 R50-FPN; retain original BGR transforms.

    v0.6 imports unused rotated/deformable operators at startup. An empty _C
    namespace lets the standard R50 model import on Windows. Calling any of
    those unavailable operators fails loudly. Standard ROIAlign and NMS use
    native torchvision operators in the unmodified upstream source.
    """

    def __init__(
        self, weight: Path, source: Path, names: tuple[str, ...], confidence: float
    ) -> None:
        sys.path.insert(0, str(source.resolve()))
        sys.modules.setdefault("detectron2._C", ModuleType("detectron2._C"))
        from detectron2.config import get_cfg
        from detectron2.data.transforms import ResizeShortestEdge
        from detectron2.modeling import build_model

        cfg = get_cfg()
        cfg.merge_from_file(
            str(source / "configs/COCO-InstanceSegmentation/mask_rcnn_R_50_FPN_3x.yaml")
        )
        cfg.MODEL.ROI_HEADS.NUM_CLASSES = len(names)
        cfg.MODEL.ROI_HEADS.SCORE_THRESH_TEST = confidence
        self.model = build_model(cfg).eval()
        checkpoint = torch.load(weight, map_location="cpu", weights_only=False)
        self.model.load_state_dict(checkpoint["model"], strict=True)
        self.resize = ResizeShortestEdge(
            [cfg.INPUT.MIN_SIZE_TEST] * 2, cfg.INPUT.MAX_SIZE_TEST
        )
        self.names = names

    def predict(self, image: NDArray[np.uint8]) -> tuple[Detection, ...]:
        from pycocotools import mask as mask_util

        h, w = image.shape[:2]
        transformed = self.resize.get_transform(image).apply_image(image)
        tensor = torch.as_tensor(
            np.ascontiguousarray(transformed.transpose(2, 0, 1))
        ).float()
        with torch.inference_mode():
            instances = self.model([{"image": tensor, "height": h, "width": w}])[0][
                "instances"
            ].to("cpu")
        detections = []
        for i, score in enumerate(instances.scores.tolist()):
            binary = instances.pred_masks[i].numpy().astype(np.uint8)
            encoded = mask_util.encode(np.asfortranarray(binary))
            box = instances.pred_boxes.tensor[i].tolist()
            match encoded["counts"]:
                case bytes() as raw_counts:
                    rle = raw_counts.decode("ascii")
                case str() as raw_counts:
                    rle = raw_counts
                case unreachable:
                    assert_never(unreachable)
            detections.append(
                Detection(
                    name=self.names[int(instances.pred_classes[i])],
                    score=score,
                    bbox_xyxy=tuple(box),
                    mask_area_ratio=float(binary.mean()),
                    mask_rle=rle,
                    mask_size=(h, w),
                )
            )
        return tuple(detections)


def overlay(
    image: NDArray[np.uint8], detections: tuple[Detection, ...]
) -> NDArray[np.uint8]:
    """Show the actual broad masks, boxes, scores, and class labels."""
    from pycocotools import mask as mask_util

    result = image.copy()
    for i, det in enumerate(detections):
        color = ((53 + 71 * i) % 255, (220 - 37 * i) % 255, (100 + 53 * i) % 255)
        if det.mask_rle is not None and det.mask_size is not None:
            binary = mask_util.decode(
                {"counts": det.mask_rle.encode("ascii"), "size": list(det.mask_size)}
            ).astype(bool)
            result[binary] = (result[binary] * 0.6 + np.array(color) * 0.4).astype(
                np.uint8
            )
        x1, y1, x2, y2 = (int(v) for v in det.bbox_xyxy)
        cv2.rectangle(result, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            result,
            f"{det.name} {det.score:.2f}",
            (x1, max(24, y1)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2,
        )
    return result
