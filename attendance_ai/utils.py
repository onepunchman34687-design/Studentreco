import cv2
import numpy as np


def read_image(path):
    """cv2.imread that also works for Windows paths with non-English characters."""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None
