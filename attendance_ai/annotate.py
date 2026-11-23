import cv2
from .utils import read_image
from .matcher import classify

GREEN, ORANGE, RED = (75, 175, 60), (0, 150, 255), (60, 60, 230)


def annotate(photo, cfg, names, img=None):
    """Draw green (matched) / orange (please check) / red (unknown) boxes like the prototype."""
    img = read_image(photo.path) if img is None else img.copy()
    big = max(img.shape[:2])
    th, fs = max(2, int(big / 900)), max(0.5, big / 2800)
    for i, f in enumerate(photo.faces):
        color, label = RED, "?"
        sc = photo.scores.get(f.roll) if f.roll else None
        if sc is not None and sc.face_idx == i:
            st = classify(sc, cfg)
            nm = names.get(f.roll, f.roll)
            if st == "present":
                color, label = GREEN, nm
            elif st == "review":
                color, label = ORANGE, nm + " ?"
        x1, y1, x2, y2 = map(int, f.bbox)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, th)
        if label != "?" or not f.low_res:
            cv2.putText(img, label, (x1, max(15, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX,
                        fs, color, max(1, th - 1), cv2.LINE_AA)
    return img
