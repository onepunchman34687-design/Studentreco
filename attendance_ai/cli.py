import argparse
import os
from .config import Config
from .pipeline import AttendanceSystem
from .export import to_csv, to_payload
from .annotate import annotate


def main():
    ap = argparse.ArgumentParser(prog="attendance_ai")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("enroll", help="enroll students from folder/<roll>__<name>/*.jpg")
    e.add_argument("--dir", required=True)
    e.add_argument("--section", required=True)

    a = sub.add_parser("attend", help="take attendance from one or more class photos")
    a.add_argument("--section", required=True)
    a.add_argument("--photos", nargs="+", required=True)
    a.add_argument("--out", default="out")
    a.add_argument("--review-as", choices=["absent", "present"], default="absent",
                   help="how to treat orange (please check) students in the CSV")

    v = sub.add_parser("evaluate", help="accuracy report + threshold sweep")
    v.add_argument("--truth", required=True)

    for p in (e, a, v):
        p.add_argument("--db", default="attendance.db")
        p.add_argument("--gpu", action="store_true")
    args = ap.parse_args()

    system = AttendanceSystem(Config(db_path=args.db, use_gpu=args.gpu))

    if args.cmd == "enroll":
        system.enroll_folder(args.dir, args.section)
    elif args.cmd == "attend":
        os.makedirs(args.out, exist_ok=True)
        res = system.take_attendance(args.photos, args.section)
        names = {s.roll: s.name for s in res.students}
        for i, ph in enumerate(res.photos):
            import cv2
            cv2.imwrite(os.path.join(args.out, f"annotated_{i}.jpg"),
                        annotate(ph, system.cfg, names))
        csv_path = to_csv(res, os.path.join(args.out, f"attendance_{res.date}.csv"),
                          unresolved=args.review_as)
        print(f"Present {len(res.present)} | Check {len(res.review)} | "
              f"Absent {len(res.absent)} | {res.percentage}%")
        for s in res.review:
            print(f"  CHECK  {s.roll} {s.name}  sim={s.similarity:.2f}")
        for s in res.absent:
            print(f"  ABSENT {s.roll} {s.name}  best_sim={s.similarity:.2f}")
        print("Saved:", csv_path)
    elif args.cmd == "evaluate":
        from .evaluate import evaluate
        evaluate(system, args.truth)


if __name__ == "__main__":
    main()
