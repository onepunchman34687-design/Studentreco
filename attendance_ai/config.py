from dataclasses import dataclass


@dataclass
class Config:
    # --- model ---
    model_pack: str = "buffalo_l"     # InsightFace pack: SCRFD detector + ArcFace recognizer
    use_gpu: bool = False
    model_root: str = ""              # "" = use ./insightface_data if present, else ~/.insightface

    # --- detection on a big class photo (tiling) ---
    det_size: tuple = (800, 800)      # detector input size per tile
    det_thresh: float = 0.35          # lower = finds more small faces, more false boxes
    tile_size: int = 800              # tile edge in pixels (kept equal to det_size => 1:1 scale)
    tile_overlap: float = 0.25        # overlap so faces on tile borders are not lost
    max_side: int = 4000              # shrink photos larger than this (speed)
    upscale_below: int = 2400         # upscale low-res photos so back-row faces get bigger
    max_upscale: float = 2.0
    min_face_px: int = 24             # faces narrower than this are too small to recognise
    nms_iou: float = 0.4              # merge duplicate detections from overlapping tiles

    # --- matching (cosine similarity of ArcFace embeddings) ---
    auto_threshold: float = 0.50      # >= this: mark PRESENT automatically (green)
    review_threshold: float = 0.35    # between review and auto: teacher must confirm (orange)
    ambiguity_margin: float = 0.05    # best vs 2nd-best student closer than this => review

    # --- enrollment ---
    min_enroll_det_score: float = 0.60
    duplicate_warn_sim: float = 0.65  # two different students this similar => warn

    db_path: str = "attendance.db"
