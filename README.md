# attendance_ai - one class photo -> present / absent

Face-recognition engine for your attendance app (InsightFace SCRFD + ArcFace, tiled detection for
small back-row faces, one-to-one Hungarian matching, green/orange/red review flow).

## Graphical app (easiest way)
    python app.py          (or double-click run_app.bat)
Tabs: **Take attendance** (choose photo -> coloured faces + student list, click a face to assign,
Present/Absent toggle per student, Save / Export CSV / Upload), **Students** (add with files or webcam,
import a folder, delete), **Report** (per-student % and day-wise CSV; red = below 75%).
Upload needs a `college_api.json` next to app.py: {"url": "...", "token": "..."} (ask the college for the API).

## Install
    pip install -r requirements.txt
First run downloads the `buffalo_l` model (~280 MB) - needs internet once.

## 1. Enroll students (5-10 photos each, varied angle/light/glasses)
    enrollment/
      015__D ANAND/1.jpg 2.jpg 3.jpg ...
      016__fazal K/1.jpg ...
    python -m attendance_ai.cli enroll --dir enrollment --section CSE-A

## 2. Take attendance (one photo, or left/centre/right shots)
    python -m attendance_ai.cli attend --section CSE-A --photos class.jpg --out out
Outputs annotated image(s) + CSV. Orange students are listed for teacher confirmation.

## 3. Measure accuracy (do this before pitching the college)
    python -m attendance_ai.cli evaluate --truth truth.json
`truth.json`:
    {"photos": [{"section": "CSE-A", "paths": ["a.jpg"], "present": ["015", "017"]}]}
Pick the lowest `auto_threshold` with 0 false accepts, then set it in `config.py`.

## Use from your Tkinter app
    from attendance_ai.config import Config
    from attendance_ai.pipeline import AttendanceSystem
    from attendance_ai.annotate import annotate
    from attendance_ai.export import to_payload, CollegeClient

    system = AttendanceSystem(Config())            # create ONCE at app start (model load is slow)
    result = system.take_attendance(path, "CSE-A") # run in a background thread, not the UI thread

    result.present / result.review / result.absent # fill your student list + stat cards
    result.percentage
    result.mark("016", "present")                  # teacher override (Present/Absent buttons)
    result.assign_face(0, face_idx, "016")         # teacher clicked a red face and picked a student
    img = annotate(result.photos[0], system.cfg, {s.roll: s.name for s in result.students})

    payload = to_payload(result, unresolved="error")   # refuses while orange students remain
    CollegeClient("https://college.example/api/attendance", token="...").push(payload)  # adapt to real API

Each `FaceResult.candidates` holds the top-3 likely students - use it for the click-to-assign popup.

## Layout
    config.py    thresholds / tiling settings      engine.py    tiled detection + embeddings
    store.py     SQLite students + embeddings      matcher.py   Hungarian matching + thresholds
    pipeline.py  AttendanceSystem (main API)       annotate.py  coloured boxes
    export.py    CSV / JSON / college upload       evaluate.py  accuracy + threshold sweep

## Notes
- Speed: a 12 MP photo is ~40-50 tiles; ~10-20 s on CPU, ~2-3 s with a GPU (`use_gpu=True`, `onnxruntime-gpu`).
- Faces narrower than `min_face_px` are never auto-matched; they show as red and fall to the teacher.
- Biometric data: keep embeddings (not photos) on a college-controlled machine, get student consent,
  restrict access, and define a deletion policy (India DPDP Act 2023).
- Only the matcher logic was tested here (synthetic embeddings). The InsightFace parts need your
  machine: run `enroll` then `attend` on a real photo and tune thresholds with `evaluate`.
