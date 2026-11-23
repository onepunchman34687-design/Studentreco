"""Run this first:  python check_setup.py   - tells you exactly what is missing."""
import sys
print("Python:", sys.version.split()[0])
if not (sys.version_info[0] == 3 and sys.version_info[1] in (9, 10, 11)):
    print("WARNING: use Python 3.10 or 3.11 for this project.")
ok = True
for mod in ["numpy", "scipy", "cv2", "onnxruntime", "insightface"]:
    try:
        m = __import__(mod)
        print(f"  OK   {mod} {getattr(m, '__version__', '')}")
    except Exception as e:
        ok = False
        print(f"  FAIL {mod}: {e}")
if not ok:
    print("\nFix the FAIL lines first (see the steps), then run this again.")
    sys.exit(1)
print("\nLoading face model (first time downloads ~280 MB, please wait)...")
from attendance_ai.engine import FaceEngine
FaceEngine()
print("\nALL GOOD. You can now enroll students.")
