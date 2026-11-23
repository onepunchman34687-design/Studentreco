"""Run: python tests/test_matcher.py   (needs only numpy + scipy)"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from attendance_ai.config import Config
from attendance_ai.store import Store
from attendance_ai.matcher import match_faces, summarize
from attendance_ai.models import PhotoResult

rng = np.random.default_rng(0)
unit = lambda v: v / np.linalg.norm(v, axis=-1, keepdims=True)
noisy = lambda v, s: unit(v + s * rng.normal(size=v.shape))

cfg = Config()
store = Store(":memory:")
ids = unit(rng.normal(size=(6, 512)))
for i in range(6):
    store.add_student(f"{i:03d}", f"S{i}", "A")
    for _ in range(3):
        store.add_embedding(f"{i:03d}", noisy(ids[i], 0.02))
g = store.gallery("A")

# students 0,1,2 present (noisy), 3 present but very blurry, 4,5 absent, plus 2 unknown strangers
faces = np.vstack([noisy(ids[0], .02), noisy(ids[1], .02), noisy(ids[2], .02),
                   noisy(ids[3], .045), unit(rng.normal(size=(2, 512)))])
info, scores = match_faces(faces, np.ones(len(faces), bool), g, cfg)
res = summarize([PhotoResult("", (0, 0), [], scores)], g, cfg, "A", "2026-10-15")
print("present:", [s.roll for s in res.present])
print("review :", [s.roll for s in res.review])
print("absent :", [s.roll for s in res.absent])
assert {"000", "001", "002"} <= {s.roll for s in res.present}
assert {"004", "005"} <= {s.roll for s in res.absent}
assert len({v.face_idx for v in scores.values()}) == len(scores), "a face was used twice"

# low-res faces must never be matched
info, scores = match_faces(faces[:1], np.array([False]), g, cfg)
assert scores == {}
print("OK")
