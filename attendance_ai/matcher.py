"""Matching logic. Pure numpy/scipy so it can be unit-tested without the face model."""
from __future__ import annotations
import numpy as np
from scipy.optimize import linear_sum_assignment
from .models import StudentScore, StudentRecord, AttendanceResult

_RANK = {"absent": 0, "review": 1, "present": 2}


def classify(sc, cfg):
    """StudentScore -> 'present' | 'review' | 'absent' using the current thresholds."""
    if sc is None:
        return "absent"
    if sc.sim >= cfg.auto_threshold and not sc.ambiguous:
        return "present"
    if sc.sim >= cfg.review_threshold:
        return "review"
    return "absent"


def match_faces(face_embs, usable, gallery, cfg):
    """
    One-to-one assignment of faces to students (Hungarian algorithm), so a student can
    never be matched to two faces and a face never to two students.
    Returns (per_face_info, scores): per_face_info[i] = (roll|None, sim, top3), scores = {roll: StudentScore}
    """
    F, N = len(face_embs), len(gallery.rolls)
    info = [(None, -1.0, []) for _ in range(F)]
    if F == 0 or N == 0 or len(gallery.emb) == 0:
        return info, {}

    sim = np.asarray(face_embs, np.float32) @ gallery.emb.T          # (F, G)
    S = np.full((F, N), -1.0, np.float32)                            # best score per STUDENT
    for j in range(N):
        idx = gallery.cols[j]
        if len(idx):
            S[:, j] = sim[:, idx].max(axis=1)
    usable = np.asarray(usable, bool)
    S_use = np.where(usable[:, None], S, -1.0)

    rows, cols = linear_sum_assignment(-S_use)
    top = np.argsort(-S, axis=1)[:, :3]
    scores = {}
    for i, j in zip(rows, cols):
        if not usable[i] or S_use[i, j] <= 0:
            continue
        s = float(S_use[i, j])
        if N > 1:
            tmp = S[i].copy()
            tmp[j] = -1.0
            other = float(tmp.max())
        else:
            other = -1.0
        amb = other >= cfg.review_threshold and (s - other) < cfg.ambiguity_margin
        cand = [(gallery.rolls[k], float(S[i, k])) for k in top[i]]
        info[i] = (gallery.rolls[j], s, cand)
        scores[gallery.rolls[j]] = StudentScore(s, int(i), bool(amb))
    return info, scores


def summarize(photos, gallery, cfg, section="", date=""):
    """Merge one or more photos into a single attendance sheet (best evidence per student wins)."""
    recs = []
    for roll, name in zip(gallery.rolls, gallery.names):
        best = StudentRecord(roll, name)
        for pi, ph in enumerate(photos):
            sc = ph.scores.get(roll)
            if sc is None:
                continue
            st = classify(sc, cfg)
            if (_RANK[st], sc.sim) > (_RANK[best.status], best.similarity):
                best = StudentRecord(roll, name, st, sc.sim, pi, sc.face_idx)
        recs.append(best)
    return AttendanceResult(section, date, recs, list(photos))
