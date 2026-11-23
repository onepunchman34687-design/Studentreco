from __future__ import annotations
import os
from datetime import date as _date
import cv2
from .utils import read_image
import numpy as np
from .config import Config
from .engine import FaceEngine
from .models import FaceResult, PhotoResult
from .matcher import match_faces, summarize
from .store import Store


class AttendanceSystem:
    """High-level API your GUI / web backend should call."""

    def __init__(self, cfg: Config | None = None, engine=None, store=None):
        self.cfg = cfg or Config()
        self.engine = engine or FaceEngine(self.cfg)
        self.store = store or Store(self.cfg.db_path)

    # ---------------- enrollment ----------------
    def enroll_image(self, roll, name, section, img_bgr):
        """Add one portrait of a student. Returns (ok, message)."""
        emb, n, score = self.engine.embed_single(img_bgr)
        if emb is None:
            return False, "no face found"
        if score < self.cfg.min_enroll_det_score:
            return False, f"face quality too low ({score:.2f})"
        warn = ""
        if n > 1:
            warn = f" (warning: {n} faces in image, used the largest)"
        g = self.store.gallery(section)
        for r, cols in zip(g.rolls, g.cols):
            if r != roll and len(cols) and float((g.emb[cols] @ emb).max()) > self.cfg.duplicate_warn_sim:
                warn += f" (warning: looks very similar to {r})"
        self.store.add_student(roll, name, section)
        self.store.add_embedding(roll, emb)
        return True, "ok" + warn

    def enroll_folder(self, folder, section, log=print):
        """folder/<roll>__<name>/*.jpg  e.g. enrollment/015__D ANAND/1.jpg"""
        for d in sorted(os.listdir(folder)):
            p = os.path.join(folder, d)
            if not os.path.isdir(p) or "__" not in d:
                continue
            roll, name = d.split("__", 1)
            ok_count = 0
            for fn in sorted(os.listdir(p)):
                if not fn.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    continue
                img = read_image(os.path.join(p, fn))
                if img is None:
                    continue
                ok, msg = self.enroll_image(roll, name, section, img)
                ok_count += ok
                if not ok or "warning" in msg:
                    log(f"  {d}/{fn}: {msg}")
            log(f"{roll} {name}: {ok_count} photo(s) enrolled")
            if ok_count < 3:
                log(f"  ! {roll} has fewer than 3 usable photos - accuracy will suffer")

    # ---------------- attendance ----------------
    def process_photo(self, photo, gallery) -> PhotoResult:
        img = photo if isinstance(photo, np.ndarray) else read_image(photo)
        if img is None:
            raise FileNotFoundError(photo)
        path = "" if isinstance(photo, np.ndarray) else photo
        dets = self.engine.detect(img)
        if dets:
            embs = np.stack([d.embedding for d in dets])
            usable = [not d.low_res for d in dets]
        else:
            embs, usable = np.zeros((0, 512), np.float32), []
        info, scores = match_faces(embs, usable, gallery, self.cfg)
        faces = [FaceResult(tuple(map(float, d.bbox)), d.score, d.low_res, r, s, c)
                 for d, (r, s, c) in zip(dets, info)]
        return PhotoResult(path, img.shape[:2], faces, scores)

    def take_attendance(self, photos, section, date=None):
        """photos: one path/array or a list (e.g. left/centre/right shots). Returns AttendanceResult."""
        if isinstance(photos, (str, np.ndarray)):
            photos = [photos]
        gallery = self.store.gallery(section)
        results = [self.process_photo(p, gallery) for p in photos]
        return summarize(results, gallery, self.cfg, section, date or _date.today().isoformat())

    def resummarize(self, result, cfg=None):
        """Re-apply thresholds to an existing result (e.g. after a slider change in the UI)."""
        g = self.store.gallery(result.section)
        return summarize(result.photos, g, cfg or self.cfg, result.section, result.date)
