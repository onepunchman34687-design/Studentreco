"""Face detection (tiled, for small back-row faces) + ArcFace embeddings via InsightFace."""
from __future__ import annotations
import os
from dataclasses import dataclass
import cv2
import numpy as np
from .config import Config


@dataclass
class DetectedFace:
    bbox: tuple
    score: float
    embedding: np.ndarray
    low_res: bool = False


def _iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def nms(faces, thr):
    kept = []
    for f in sorted(faces, key=lambda f: -f.score):
        if all(_iou(f.bbox, k.bbox) < thr for k in kept):
            kept.append(f)
    return kept


class FaceEngine:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or Config()
        from insightface.app import FaceAnalysis   # imported lazily (heavy)
        providers = (["CUDAExecutionProvider", "CPUExecutionProvider"]
                     if self.cfg.use_gpu else ["CPUExecutionProvider"])
        self.app = FaceAnalysis(name=self.cfg.model_pack, root=self._model_root(), providers=providers,
                                allowed_modules=["detection", "recognition"])
        self.app.prepare(ctx_id=0 if self.cfg.use_gpu else -1,
                         det_thresh=self.cfg.det_thresh, det_size=self.cfg.det_size)

    def _model_root(self):
        """Portable mode: models live in <project>/insightface_data (copied with the folder)."""
        if self.cfg.model_root:
            return self.cfg.model_root
        local = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "insightface_data")
        return local if os.path.isdir(local) else os.path.expanduser("~/.insightface")

    # ---------- class photo ----------
    def _tiles(self, h, w):
        t = self.cfg.tile_size
        if h <= t and w <= t:
            return [(0, 0, w, h)]
        step = max(1, int(t * (1 - self.cfg.tile_overlap)))

        def axis(n):
            pts = list(range(0, max(n - t, 0) + 1, step))
            if pts[-1] + t < n:
                pts.append(n - t)
            return pts
        return [(x, y, min(x + t, w), min(y + t, h)) for y in axis(h) for x in axis(w)]

    def detect(self, img_bgr):
        """Return list[DetectedFace] with bboxes in ORIGINAL image coordinates."""
        c = self.cfg
        h0, w0 = img_bgr.shape[:2]
        m = max(h0, w0)
        scale = 1.0
        if m > c.max_side:
            scale = c.max_side / m
        elif m < c.upscale_below:
            scale = min(c.max_upscale, c.upscale_below / m)
        img = img_bgr if scale == 1.0 else cv2.resize(
            img_bgr, None, fx=scale, fy=scale,
            interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)
        h, w = img.shape[:2]

        found, edge = [], 3
        for (x0, y0, x1, y1) in self._tiles(h, w):
            tile = img[y0:y1, x0:x1]
            th, tw = tile.shape[:2]
            for f in self.app.get(tile):
                b = f.bbox
                # drop faces cut by an inner tile border; the neighbouring tile sees them whole
                if ((b[0] <= edge and x0 > 0) or (b[1] <= edge and y0 > 0) or
                        (b[2] >= tw - edge and x1 < w) or (b[3] >= th - edge and y1 < h)):
                    continue
                box = ((b[0] + x0) / scale, (b[1] + y0) / scale,
                       (b[2] + x0) / scale, (b[3] + y0) / scale)
                emb = getattr(f, "normed_embedding", None)
                if emb is None:
                    continue
                found.append(DetectedFace(box, float(f.det_score), emb.astype(np.float32),
                                          low_res=(box[2] - box[0]) < c.min_face_px))
        return nms(found, c.nms_iou)

    # ---------- enrollment photo (one student, close-up) ----------
    def embed_single(self, img_bgr):
        """Largest face in a portrait. Returns (embedding|None, n_faces, det_score)."""
        h, w = img_bgr.shape[:2]
        if max(h, w) > 1600:
            s = 1600 / max(h, w)
            img_bgr = cv2.resize(img_bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        faces = self.app.get(img_bgr)
        if not faces:
            return None, 0, 0.0
        f = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        return f.normed_embedding.astype(np.float32), len(faces), float(f.det_score)
