from flask import Flask, jsonify, request
import xml.etree.ElementTree as ET
import sqlite3
import os

app = Flask(__name__)


def get_db_connection():
    """
    Establishes a connection to the SQLite database.
    """
    conn = sqlite3.connect('tag_genius.db')
    conn.row_factory = sqlite3.Row
    return conn


@app.cli.command('init-db')
def init_db():
    """
    Initializes the database by creating the tracks table.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            artist TEXT,
            bpm REAL,
            track_key TEXT,
            genre TEXT,
            label TEXT,
            comments TEXT,
            grouping TEXT,
            tags TEXT
        );
    """)
    conn.commit()
    conn.close()
    print('Database initialized successfully.')


def insert_track_data(name, artist, bpm, track_key, genre, label, comments, grouping, tags):
    """
    Inserts a single track's metadata into the database.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check if a track with the same name and artist already exists to avoid duplicates.
        cursor.execute("SELECT id FROM tracks WHERE name = ? AND artist = ?", (name, artist))
        existing_track = cursor.fetchone()

        if existing_track:
            print(f"Skipping duplicate track: {name} by {artist}")
            return

        # Insert the new track data into the tracks table.
        cursor.execute("""
            INSERT INTO tracks (name, artist, bpm, track_key, genre, label, comments, grouping, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, artist, bpm, track_key, genre, label, comments, grouping, tags))

        conn.commit()
        print(f"Successfully inserted: {name} by {artist}")

    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error: {e}")
    finally:
        conn.close()


@app.route('/')
def hello_ai():
    """
    A simple test route to ensure the server is running.
    """
    return 'Hello, Ai!'


@app.route('/tracks', methods=['GET'])
def get_tracks():
    """
    Retrieves all music tracks from the database.
    """
    conn = get_db_connection()
    tracks = conn.execute('SELECT * FROM tracks').fetchall()
    conn.close()

    tracks_list = [dict(row) for row in tracks]
    return jsonify(tracks_list)


@app.route('/tracks', methods=['POST'])
def add_track():
    """
    Adds a new track to the database from a JSON payload.
    """
    data = request.get_json()
    name = data.get('name')
    artist = data.get('artist')

    if not name or not artist:
        return jsonify({"error": "Name and artist are required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("INSERT INTO tracks (name, artist) VALUES (?, ?)", (name, artist))
        conn.commit()
        return jsonify({"message": "Track added successfully."}), 201
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route('/tracks/<int:track_id>', methods=['GET'])
def get_track(track_id):
    """
    Retrieves a single track by its unique ID.
    """
    conn = get_db_connection()
    track = conn.execute('SELECT * FROM tracks WHERE id = ?', (track_id,)).fetchone()
    conn.close()

    if track is None:
        return jsonify({"error": "Track not found"}), 404

    return jsonify(dict(track))


@app.route('/tracks/<int:track_id>', methods=['DELETE'])
def delete_track(track_id):
    """
    Deletes a single track by its unique ID.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM tracks WHERE id = ?", (track_id,))
        track = cursor.fetchone()

        if track is None:
            return jsonify({"error": "Track not found"}), 404

        cursor.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
        conn.commit()
        return jsonify({"message": "Track deleted successfully"}), 200
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route('/tracks/<int:track_id>', methods=['PUT'])
def update_track(track_id):
    """
    Updates an existing track by its unique ID.
    """
    data = request.get_json()
    name = data.get('name')
    artist = data.get('artist')

    if not name or not artist:
        return jsonify({"error": "Name and artist are required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM tracks WHERE id = ?", (track_id,))
        track = cursor.fetchone()

        if track is None:
            return jsonify({"error": "Track not found"}), 404

        cursor.execute("UPDATE tracks SET name = ?, artist = ? WHERE id = ?",
                       (name, artist, track_id))

        conn.commit()
        return jsonify({"message": "Track updated successfully"}), 200
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route('/upload_library', methods=['POST'])
def upload_library():
    """
    Handles the upload of a music library XML file and starts the parsing process.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file:
        file_path = os.path.join("uploads", file.filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        file.save(file_path)

        # Call the processing function after saving the file
        processing_result = process_library(file_path)

        return jsonify(processing_result), 200

    return jsonify({"error": "An unknown error occurred"}), 500


def process_library(xml_path):
    """
    Parses the XML file, extracts track data, and inserts it into the database.
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        collection = root.find('COLLECTION')
        tracks = collection.findall('TRACK')

        print(f"Found {len(tracks)} tracks in the XML file.")

        for track in tracks:
            track_name = track.get('Name')
            artist = track.get('Artist')
            bpm = track.get('AverageBpm')
            track_key = track.get('Tonality')
            genre = track.get('Genre')
            label = track.get('Label')
            comments = track.get('Comments')
            grouping = track.get('Grouping')

            tags_element = track.find('TAGS')
            tags = []
            if tags_element is not None:
                for tag in tags_element.findall('TAG'):
                    tags.append(tag.get('NAME'))
            tags_string = ', '.join(tags)

            # Insert the track data into the database
            insert_track_data(track_name, artist, bpm, track_key, genre, label, comments, grouping, tags_string)

        return {"message": "XML file processed and data inserted into the database."}

    except Exception as e:
        return {"error": f"Failed to process XML: {e}"}


if __name__ == '__main__':
    app.run(debug=True)
