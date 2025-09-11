import os
import sqlite3
import xml.etree.ElementTree as ET
import json
import requests
from flask import Flask, jsonify, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Global variable to store the user-defined tag limit for 'nice-to-have' categories.
# Default is set to 1 for the 'Essential' level.
tag_limit = 1


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
                   CREATE TABLE IF NOT EXISTS tracks
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       name
                       TEXT
                       NOT
                       NULL,
                       artist
                       TEXT,
                       bpm
                       REAL,
                       track_key
                       TEXT,
                       genre
                       TEXT,
                       label
                       TEXT,
                       comments
                       TEXT,
                       grouping
                       TEXT,
                       tags
                       TEXT
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
        # The 'tags' are now expected to be a JSON string.
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


def call_lexicon_api(artist, name):
    """
    Calls the Lexicon Local API to get enriched track data.

    This function now uses the `/search/tracks` endpoint for a more
    direct and efficient search, as specified in the Lexicon API reference.
    """
    api_url = 'http://localhost:48624/v1/search/tracks'

    try:
        # Use the /search/tracks endpoint with filter parameters.
        params = {
            "filter": {
                "artist": artist,
                "title": name
            }
        }
        response = requests.get(api_url, json=params)
        response.raise_for_status()
        lexicon_data = response.json()

        # Return the first matching track if found, otherwise an empty dict.
        tracks = lexicon_data.get('tracks', [])
        return tracks[0] if tracks else {}

    except requests.exceptions.RequestException as e:
        print(f"Lexicon API call failed: {e}")
        return {}


def call_llm_for_tags(track_data):
    """
    Calls an LLM to generate a structured set of tags for a music track,
    using enriched data from Lexicon.

    Args:
        track_data (dict): A dictionary containing track metadata, including
                           any data enriched by Lexicon.

    Returns:
        dict: A dictionary of generated tags, categorized by type.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY environment variable not set. Using mock tags.")
        return {
            "primary_genre": ["techno"],
            "sub_genre": ["hard techno", "industrial"],
            "energy_vibe": ["peak hour", "aggressive"],
            "situation_environment": ["main floor"],
            "components": ["vocal", "remix"],
            "time_period": ["2010s"]
        }

    global tag_limit

    # The prompt now explicitly asks for a specific number of tags for each category,
    # controlled by the user-defined tag_limit.
    prompt_text = (
        f"You are a master music curator and a 'Tag Genius.' Your mission is to provide concise, "
        f"structured, and expertly curated tags for a DJ's library. For each category, "
        f"provide exactly {tag_limit} tags unless a category has fewer relevant tags, in which "
        f"case provide all of them. Here is a track for you to tag:\n\n"
        f"Track: '{track_data.get('ARTIST')} - {track_data.get('TITLE')}'\n"
        f"Existing Genre: {track_data.get('GENRE')}\n"
        f"Year: {track_data.get('YEAR')}\n"
        f"Lexicon Data: {json.dumps(track_data.get('lexicon_data', {}))}\n\n"
        f"Your task is to provide tags as a JSON object with the following keys: 'primary_genre', "
        f"'sub_genre', 'energy_vibe', 'situation_environment', 'components', and 'time_period'. "
        f"Each key must map to a list of strings. Each tag should be concise and in lowercase. "
        f"Only include 'components' and 'time_period' if they are highly relevant and "
        f"genuinely add value. Respond with a JSON object only, no additional text."
    )

    api_url = "https://api.openai.com/v1/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    # The payload is structured for the OpenAI Chat Completions API.
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": prompt_text}
        ],
        "response_format": {"type": "json_object"}
    }

    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        api_result = response.json()

        text_part = api_result.get("choices", [{}])[0].get("message", {}).get("content")

        if text_part:
            generated_data = json.loads(text_part)
            return generated_data
        else:
            print("LLM response was not in the expected format.")
            return {}

    except requests.exceptions.RequestException as e:
        print(f"API call failed: {e}")
        return {}
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON from LLM response: {e}")
        return {}


@app.route('/')
def hello_ai():
    """
    A simple test route to ensure the server is running.
    """
    return 'Hello, Ai!'


@app.route('/tracks', methods=['GET'])
def get_tracks():
    """
    Retrieves all music tracks from the database,
    deserializing the 'tags' column from a JSON string to a JSON object.
    """
    conn = get_db_connection()
    tracks = conn.execute('SELECT * FROM tracks').fetchall()
    conn.close()

    tracks_list = [dict(row) for row in tracks]
    for track in tracks_list:
        if track.get('tags'):
            try:
                track['tags'] = json.loads(track['tags'])
            except json.JSONDecodeError:
                # Handle cases where tags might not be valid JSON
                track['tags'] = {"error": "Invalid JSON"}

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

    track_dict = dict(track)
    if track_dict.get('tags'):
        try:
            track_dict['tags'] = json.loads(track['tags'])
        except json.JSONDecodeError:
            track_dict['tags'] = {"error": "Invalid JSON"}

    return jsonify(track_dict)


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


@app.route('/set_tag_limit', methods=['POST'])
def set_tag_limit():
    """
    Sets the global tag limit for the 'nice-to-have' categories.
    """
    global tag_limit
    data = request.get_json()
    new_limit = data.get('max_tags')

    if new_limit is None or not isinstance(new_limit, int) or new_limit < 0:
        return jsonify({"error": "Invalid tag limit provided. Must be a non-negative integer."}), 400

    tag_limit = new_limit
    print(f"Tag limit successfully updated to: {tag_limit}")
    return jsonify({"message": f"Tag limit updated to {new_limit}"}), 200


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

            # First, call the Lexicon API to enrich the track data
            lexicon_data = call_lexicon_api(artist, track_name)

            # Combine the original XML data with the enriched data from Lexicon
            track_data = {
                'ARTIST': artist,
                'TITLE': track_name,
                'GENRE': genre,
                'YEAR': track.get('Year'),
                'lexicon_data': lexicon_data
            }

            # Now, call the LLM for structured tags using the enriched data
            generated_tags = call_llm_for_tags(track_data)
            tags_string = json.dumps(generated_tags)

            # Insert the track data into the database
            insert_track_data(track_name, artist, bpm, track_key, genre, label, comments, grouping, tags_string)

        return {"message": "XML file processed and data inserted into the database."}

    except Exception as e:
        return {"error": f"Failed to process XML: {e}"}


import os
import sqlite3
import xml.etree.ElementTree as ET
import json
import requests
from flask import Flask, jsonify, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Global variable to store the user-defined tag limit for 'nice-to-have' categories.
# Default is set to 1 for the 'Essential' level.
tag_limit = 1


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
                   CREATE TABLE IF NOT EXISTS tracks
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       name
                       TEXT
                       NOT
                       NULL,
                       artist
                       TEXT,
                       bpm
                       REAL,
                       track_key
                       TEXT,
                       genre
                       TEXT,
                       label
                       TEXT,
                       comments
                       TEXT,
                       grouping
                       TEXT,
                       tags
                       TEXT
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
        # The 'tags' are now expected to be a JSON string.
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


def call_lexicon_api(artist, name):
    """
    Calls the Lexicon Local API to get enriched track data.

    This function now uses the `/search/tracks` endpoint for a more
    direct and efficient search, as specified in the Lexicon API reference.
    """
    api_url = 'http://localhost:48624/v1/search/tracks'

    try:
        # Use the /search/tracks endpoint with filter parameters.
        params = {
            "filter": {
                "artist": artist,
                "title": name
            }
        }
        response = requests.get(api_url, json=params)
        response.raise_for_status()
        lexicon_data = response.json()

        # Return the first matching track if found, otherwise an empty dict.
        tracks = lexicon_data.get('tracks', [])
        return tracks[0] if tracks else {}

    except requests.exceptions.RequestException as e:
        print(f"Lexicon API call failed: {e}")
        return {}


def call_llm_for_tags(track_data):
    """
    Calls an LLM to generate a structured set of tags for a music track,
    using enriched data from Lexicon.

    Args:
        track_data (dict): A dictionary containing track metadata, including
                           any data enriched by Lexicon.

    Returns:
        dict: A dictionary of generated tags, categorized by type.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY environment variable not set. Using mock tags.")
        return {
            "primary_genre": ["techno"],
            "sub_genre": ["hard techno", "industrial"],
            "energy_vibe": ["peak hour", "aggressive"],
            "situation_environment": ["main floor"],
            "components": ["vocal", "remix"],
            "time_period": ["2010s"]
        }

    global tag_limit

    # The prompt now explicitly asks for a specific number of tags for each category,
    # controlled by the user-defined tag_limit.
    prompt_text = (
        f"You are a master music curator and a 'Tag Genius.' Your mission is to provide concise, "
        f"structured, and expertly curated tags for a DJ's library. For each category, "
        f"provide exactly {tag_limit} tags unless a category has fewer relevant tags, in which "
        f"case provide all of them. Here is a track for you to tag:\n\n"
        f"Track: '{track_data.get('ARTIST')} - {track_data.get('TITLE')}'\n"
        f"Existing Genre: {track_data.get('GENRE')}\n"
        f"Year: {track_data.get('YEAR')}\n"
        f"Lexicon Data: {json.dumps(track_data.get('lexicon_data', {}))}\n\n"
        f"Your task is to provide tags as a JSON object with the following keys: 'primary_genre', "
        f"'sub_genre', 'energy_vibe', 'situation_environment', 'components', and 'time_period'. "
        f"Each key must map to a list of strings. Each tag should be concise and in lowercase. "
        f"Only include 'components' and 'time_period' if they are highly relevant and "
        f"genuinely add value. Respond with a JSON object only, no additional text."
    )

    api_url = "https://api.openai.com/v1/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    # The payload is structured for the OpenAI Chat Completions API.
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": prompt_text}
        ],
        "response_format": {"type": "json_object"}
    }

    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        api_result = response.json()

        text_part = api_result.get("choices", [{}])[0].get("message", {}).get("content")

        if text_part:
            generated_data = json.loads(text_part)
            return generated_data
        else:
            print("LLM response was not in the expected format.")
            return {}

    except requests.exceptions.RequestException as e:
        print(f"API call failed: {e}")
        return {}
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON from LLM response: {e}")
        return {}


@app.route('/')
def hello_ai():
    """
    A simple test route to ensure the server is running.
    """
    return 'Hello, Ai!'


@app.route('/tracks', methods=['GET'])
def get_tracks():
    """
    Retrieves all music tracks from the database,
    deserializing the 'tags' column from a JSON string to a JSON object.
    """
    conn = get_db_connection()
    tracks = conn.execute('SELECT * FROM tracks').fetchall()
    conn.close()

    tracks_list = [dict(row) for row in tracks]
    for track in tracks_list:
        if track.get('tags'):
            try:
                track['tags'] = json.loads(track['tags'])
            except json.JSONDecodeError:
                # Handle cases where tags might not be valid JSON
                track['tags'] = {"error": "Invalid JSON"}

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

    track_dict = dict(track)
    if track_dict.get('tags'):
        try:
            track_dict['tags'] = json.loads(track['tags'])
        except json.JSONDecodeError:
            track_dict['tags'] = {"error": "Invalid JSON"}

    return jsonify(track_dict)


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


@app.route('/set_tag_limit', methods=['POST'])
def set_tag_limit():
    """
    Sets the global tag limit for the 'nice-to-have' categories.
    """
    global tag_limit
    data = request.get_json()
    new_limit = data.get('max_tags')

    if new_limit is None or not isinstance(new_limit, int) or new_limit < 0:
        return jsonify({"error": "Invalid tag limit provided. Must be a non-negative integer."}), 400

    tag_limit = new_limit
    print(f"Tag limit successfully updated to: {tag_limit}")
    return jsonify({"message": f"Tag limit updated to {new_limit}"}), 200


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

            # First, call the Lexicon API to enrich the track data
            lexicon_data = call_lexicon_api(artist, track_name)

            # Combine the original XML data with the enriched data from Lexicon
            track_data = {
                'ARTIST': artist,
                'TITLE': track_name,
                'GENRE': genre,
                'YEAR': track.get('Year'),
                'lexicon_data': lexicon_data
            }

            # Now, call the LLM for structured tags using the enriched data
            generated_tags = call_llm_for_tags(track_data)
            tags_string = json.dumps(generated_tags)

            # Insert the track data into the database
            insert_track_data(track_name, artist, bpm, track_key, genre, label, comments, grouping, tags_string)

        return {"message": "XML file processed and data inserted into the database."}

    except Exception as e:
        return {"error": f"Failed to process XML: {e}"}


if __name__ == '__main__':
    app.run(debug=True)

if __name__ == '__main__':
    app.run(debug=True)
