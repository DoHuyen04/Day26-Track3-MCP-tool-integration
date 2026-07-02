"""Database initialization: create tables and insert seed data."""

import sqlite3
import os


DROP_SQL = """
DROP TABLE IF EXISTS enrollments;
DROP TABLE IF EXISTS courses;
DROP TABLE IF EXISTS students;
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    cohort TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    instructor TEXT NOT NULL,
    credits INTEGER DEFAULT 3,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    score REAL,
    enrolled_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    UNIQUE(student_id, course_id)
);
"""

SEED_SQL = """
-- Students
INSERT OR IGNORE INTO students (id, name, cohort, email) VALUES
    (1, 'Alice Nguyen',   'A1', 'alice@example.com'),
    (2, 'Bob Tran',       'A1', 'bob@example.com'),
    (3, 'Carol Le',       'A2', 'carol@example.com'),
    (4, 'David Pham',     'A2', 'david@example.com'),
    (5, 'Eve Hoang',      'B1', 'eve@example.com'),
    (6, 'Frank Vu',       'B1', 'frank@example.com'),
    (7, 'Grace Dang',     'A1', 'grace@example.com'),
    (8, 'Hank Bui',       'A2', 'hank@example.com');

-- Courses
INSERT OR IGNORE INTO courses (id, name, instructor, credits) VALUES
    (1, 'Mathematics',    'Dr. Smith',   3),
    (2, 'Physics',        'Dr. Jones',   4),
    (3, 'Programming',    'Dr. Lee',     3),
    (4, 'Databases',      'Dr. Chen',    3),
    (5, 'English',        'Dr. Brown',   2);

-- Enrollments
INSERT OR IGNORE INTO enrollments (id, student_id, course_id, score) VALUES
    (1,  1, 1, 8.5),
    (2,  1, 3, 9.0),
    (3,  2, 1, 7.0),
    (4,  2, 2, 6.5),
    (5,  2, 3, 8.0),
    (6,  3, 1, 9.5),
    (7,  3, 4, 8.0),
    (8,  4, 2, 5.5),
    (9,  4, 4, 7.5),
    (10, 4, 5, 8.0),
    (11, 5, 3, 6.0),
    (12, 5, 4, 7.0),
    (13, 6, 1, 4.5),
    (14, 6, 5, 9.0),
    (15, 7, 2, 8.5),
    (16, 7, 3, 9.5),
    (17, 8, 4, 6.0),
    (18, 8, 2, 7.0);
"""

DB_FILENAME = "lab.db"


def create_database(db_path=None):
    """
    Create the SQLite database file, apply the schema, and insert seed data.

    Args:
        db_path: Optional path to the database file.
                 Defaults to the same directory as this script (lab.db).

    Returns:
        Absolute path to the created database file.
    """
    if db_path is None:
        db_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(db_dir, DB_FILENAME)

    conn = sqlite3.connect(db_path)
    conn.executescript(DROP_SQL)
    conn.executescript(SCHEMA_SQL)
    conn.executescript(SEED_SQL)
    conn.commit()
    conn.close()

    return os.path.abspath(db_path)


if __name__ == "__main__":
    path = create_database()
    print(f"Database created at: {path}")
