"""SQLite store: students, face embeddings (no raw photos kept), saved attendance."""
from __future__ import annotations
import sqlite3
from dataclasses import dataclass
import numpy as np

EMB_DIM = 512


@dataclass
class Gallery:
    rolls: list
    names: list
    emb: np.ndarray        # (G, 512) L2-normalised, one row per enrolled photo
    cols: list             # cols[j] = np.array of rows in emb belonging to student j


class Store:
    def __init__(self, path="attendance.db"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS students(
                roll TEXT PRIMARY KEY, name TEXT NOT NULL, section TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS embeddings(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                roll TEXT NOT NULL REFERENCES students(roll) ON DELETE CASCADE,
                vec BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS attendance(
                date TEXT NOT NULL, section TEXT NOT NULL, roll TEXT NOT NULL,
                status TEXT NOT NULL, similarity REAL, source TEXT,
                PRIMARY KEY(date, section, roll));
        """)
        self.db.execute("PRAGMA foreign_keys=ON")

    # ---- students ----
    def add_student(self, roll, name, section):
        self.db.execute(
            "INSERT INTO students(roll,name,section) VALUES(?,?,?) "
            "ON CONFLICT(roll) DO UPDATE SET name=excluded.name, section=excluded.section",
            (roll, name, section))
        self.db.commit()

    def add_embedding(self, roll, vec):
        v = np.asarray(vec, dtype=np.float32)
        v = v / (np.linalg.norm(v) + 1e-9)
        self.db.execute("INSERT INTO embeddings(roll,vec) VALUES(?,?)", (roll, v.tobytes()))
        self.db.commit()

    def clear_embeddings(self, roll):
        self.db.execute("DELETE FROM embeddings WHERE roll=?", (roll,))
        self.db.commit()

    def delete_student(self, roll):
        self.db.execute("DELETE FROM embeddings WHERE roll=?", (roll,))
        self.db.execute("DELETE FROM students WHERE roll=?", (roll,))
        self.db.commit()

    def sections(self):
        return [r[0] for r in self.db.execute("SELECT DISTINCT section FROM students ORDER BY section")]

    def roster(self, section=None):
        q, a = "SELECT roll,name FROM students", ()
        if section:
            q, a = q + " WHERE section=?", (section,)
        return self.db.execute(q + " ORDER BY roll", a).fetchall()

    def embedding_count(self, roll):
        return self.db.execute("SELECT COUNT(*) FROM embeddings WHERE roll=?", (roll,)).fetchone()[0]

    def gallery(self, section=None) -> Gallery:
        roster = self.roster(section)
        rolls, names, rows, cols = [], [], [], []
        for roll, name in roster:
            vecs = [np.frombuffer(b, dtype=np.float32)
                    for (b,) in self.db.execute("SELECT vec FROM embeddings WHERE roll=?", (roll,))]
            start = len(rows)
            rows.extend(vecs)
            rolls.append(roll)
            names.append(name)
            cols.append(np.arange(start, start + len(vecs)))
        emb = np.stack(rows) if rows else np.zeros((0, EMB_DIM), np.float32)
        return Gallery(rolls, names, emb, cols)

    # ---- saved attendance ----
    def has_attendance(self, date, section):
        return self.db.execute("SELECT 1 FROM attendance WHERE date=? AND section=? LIMIT 1",
                               (date, section)).fetchone() is not None

    def save_attendance(self, date, section, records):
        """records: iterable of (roll, status, similarity, source). Replaces that day's sheet."""
        self.db.execute("DELETE FROM attendance WHERE date=? AND section=?", (date, section))
        self.db.executemany(
            "INSERT INTO attendance(date,section,roll,status,similarity,source) VALUES(?,?,?,?,?,?)",
            [(date, section, r, s, float(sim), src) for r, s, sim, src in records])
        self.db.commit()

    def report(self, section):
        """[(roll, name, days_present, days_total)] over all saved days."""
        q = """SELECT s.roll, s.name,
                      COALESCE(SUM(a.status='present'),0), COUNT(a.date)
               FROM students s
               LEFT JOIN attendance a ON a.roll=s.roll AND a.section=s.section
               WHERE s.section=? GROUP BY s.roll, s.name ORDER BY s.roll"""
        return self.db.execute(q, (section,)).fetchall()

    def matrix(self, section):
        """(dates, [(roll, name, [status per date])]) for a day-wise sheet."""
        dates = [d for (d,) in self.db.execute(
            "SELECT DISTINCT date FROM attendance WHERE section=? ORDER BY date", (section,))]
        st = {(r, d): s for r, d, s in self.db.execute(
            "SELECT roll,date,status FROM attendance WHERE section=?", (section,))}
        rows = [(roll, name, [st.get((roll, d), "") for d in dates])
                for roll, name in self.roster(section)]
        return dates, rows
