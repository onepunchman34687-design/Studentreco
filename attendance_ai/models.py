from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FaceResult:
    bbox: tuple                      # x1, y1, x2, y2 in ORIGINAL photo pixels
    det_score: float
    low_res: bool = False            # too small to recognise reliably
    roll: Optional[str] = None       # student this face was assigned to (may still be weak)
    sim: float = -1.0
    candidates: list = field(default_factory=list)   # [(roll, sim)] top-3, for click-to-assign UI


@dataclass
class StudentScore:
    sim: float
    face_idx: int
    ambiguous: bool = False


@dataclass
class PhotoResult:
    path: str
    size: tuple                      # (height, width)
    faces: list                      # list[FaceResult]
    scores: dict                     # roll -> StudentScore (faces assigned one-to-one)


@dataclass
class StudentRecord:
    roll: str
    name: str
    status: str = "absent"           # present | review | absent
    similarity: float = -1.0
    photo_idx: int = -1
    face_idx: int = -1
    source: str = "auto"             # auto | manual


@dataclass
class AttendanceResult:
    section: str
    date: str
    students: list                   # list[StudentRecord]
    photos: list                     # list[PhotoResult]

    def _by(self, status):
        return [s for s in self.students if s.status == status]

    @property
    def present(self):
        return self._by("present")

    @property
    def review(self):
        return self._by("review")

    @property
    def absent(self):
        return self._by("absent")

    @property
    def percentage(self):
        n = len(self.students)
        return round(100.0 * len(self.present) / n, 1) if n else 0.0

    def _get(self, roll):
        for s in self.students:
            if s.roll == roll:
                return s
        raise KeyError(roll)

    def mark(self, roll, status):
        """Teacher override: status in {'present','absent'}."""
        s = self._get(roll)
        s.status, s.source = status, "manual"

    def assign_face(self, photo_idx, face_idx, roll):
        """Teacher clicked a red/orange face and picked a student."""
        s = self._get(roll)
        s.status, s.source = "present", "manual"
        s.photo_idx, s.face_idx = photo_idx, face_idx
