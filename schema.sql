DROP TABLE IF EXISTS tracks;

CREATE TABLE tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    bpm REAL,
    track_key TEXT,
    tags TEXT
);

INSERT INTO tracks (name, description, bpm, track_key, tags) VALUES ('One More Time', 'A classic house track by Daft Punk', 123.5, 'A Major', 'House, French House, Vocal House, Electronic');