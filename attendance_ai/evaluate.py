"""
Measure accuracy on real class photos so you can pick thresholds and show numbers to the college.

truth.json:
{"photos": [{"section": "CSE-A", "paths": ["a_left.jpg", "a_right.jpg"], "present": ["015", "017"]}]}
"""
import json
from dataclasses import replace
import numpy as np
from .matcher import summarize


def evaluate(system, truth_path, thresholds=None, log=print):
    thresholds = thresholds if thresholds is not None else np.arange(0.30, 0.71, 0.05)
    truth = json.load(open(truth_path, encoding="utf-8"))
    runs = []
    for item in truth["photos"]:
        g = system.store.gallery(item["section"])
        photos = [system.process_photo(p, g) for p in item["paths"]]
        runs.append((g, photos, set(item["present"])))

    log(f"{'auto_thr':>8} {'recall':>7} {'false_acc':>9} {'review%':>8} {'wrongly_absent':>14}")
    rows = []
    for t in thresholds:
        cfg = replace(system.cfg, auto_threshold=float(t),
                      review_threshold=min(system.cfg.review_threshold, float(t)))
        tp = fp = fn = rev = total = 0
        for g, photos, truth_present in runs:
            res = summarize(photos, g, cfg)
            for s in res.students:
                total += 1
                is_p = s.roll in truth_present
                if s.status == "present":
                    tp += is_p
                    fp += (not is_p)
                elif s.status == "review":
                    rev += 1
                elif is_p:
                    fn += 1
        n_present = sum(len(tp_) for _, _, tp_ in runs)
        recall = tp / n_present if n_present else 0.0
        rows.append((float(t), recall, fp, rev / total if total else 0, fn))
        log(f"{t:8.2f} {recall:7.1%} {fp:9d} {rev / total if total else 0:8.1%} {fn:14d}")
    log("\nPick the lowest auto_thr with false_acc == 0 (proxy attendance is the costly error).")
    return rows
