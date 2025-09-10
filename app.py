from flask import Flask, jsonify, request
import xml.etree.ElementTree as ET
import sqlite3
import os

app = Flask(__name__)

'''
Creates a new connection to the database.
'''


def get_db_connection():
    """
    Establishes a connection to the SQLite database.
    """
    conn = sqlite3.connect('tag_genius.db')
    conn.row_factory = sqlite3.Row
    return conn


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
    description = data.get('description')

    if not name or not description:
        return jsonify({"error": "Name and description are required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("INSERT INTO tracks (name, description) VALUES (?, ?)", (name, description))
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
    description = data.get('description')

    if not name or not description:
        return jsonify({"error": "Name and description are required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM tracks WHERE id = ?", (track_id,))
        track = cursor.fetchone()

        if track is None:
            return jsonify({"error": "Track not found"}), 404

        cursor.execute("UPDATE tracks SET name = ?, description = ? WHERE id = ?",
                       (name, description, track_id))

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
    #This code parses the XML file
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        collection = root.find('COLLECTION')
        tracks = collection.findall('TRACK')

        print(f"Found {len(tracks)} tracks in the XML file.")

        #loop through each track and print all its attributes
        for track in tracks:
            print("\n--- New Track ---")
            for key, value in track.attrib.items():
                print (f"{key}: {value}")

        return {"message": "XML attributes printed to console."}

    except Exception as e:
        return {"error": f"Failed to process XML: {e}"}


if __name__ == '__main__':
    app.run(debug=True)