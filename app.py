from flask import Flask, request, jsonify, send_file
import sqlite3
import xml.etree.ElementTree as ET
import openai
import json
import os

# Initialize Flask app
app = Flask(__name__)

# --- Database & LLM Setup ---
DB_NAME = 'tag_genius.db'


def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def create_database():
    """Creates the necessary tables if they don't exist."""
    conn = get_db_connection()
    conn.execute('''
                 CREATE TABLE IF NOT EXISTS tracks
                 (
                     id
                     TEXT
                     PRIMARY
                     KEY,
                     artist
                     TEXT,
                     title
                     TEXT,
                     track_id
                     INTEGER,
                     genre
                     TEXT,
                     comments
                     TEXT,
                     grouping
                     TEXT,
                     llm_tags
                     TEXT
                 )
                 ''')
    conn.commit()
    conn.close()


# Initial database creation
create_database()


# --- Utility Functions ---

def parse_rekordbox_xml(xml_content):
    """
    Parses Rekordbox XML content and extracts relevant track data.
    """
    root = ET.fromstring(xml_content)
    # Define the namespace map
    namespace = {'ns': 'http://www.rekordbox.com'}
    collection = root.find('.//ns:COLLECTION', namespace)
    tracks = []
    if collection is not None:
        for track_node in collection.findall('.//ns:TRACK', namespace):
            track_data = track_node.attrib
            tracks.append({
                'id': track_data.get('Location'),
                'artist': track_data.get('Artist'),
                'title': track_data.get('Name'),
                'track_id': track_data.get('TrackID'),
                'genre': track_data.get('Genre'),
                'comments': track_data.get('Comments'),
                'grouping': track_data.get('Grouping')
            })
    return tracks


def call_llm_for_tags(track_data, tag_config):
    """
    Generates tags for a single track using an LLM.
    The prompt is now more precise, based on the tag_config dictionary.
    """
    prompt = f"""
    You are a master music curator, specializing in providing precise and accurate tags for a DJ's music library.
    Your task is to analyze the provided track details and generate a list of tags for the following categories:
    - Primary Genre
    - Sub-genre
    - Energy/Vibe
    - Situation/Environment
    - Components
    - Time Period

    For each category, provide exactly the number of tags specified below. If a category has fewer relevant tags, provide all of them. Do not exceed the specified number.

    Primary Genre: exactly {tag_config.get('primary_genre', 1)} tag.
    Sub-genre: exactly {tag_config.get('sub_genre', 1)} tags.
    Energy/Vibe: exactly {tag_config.get('energy_vibe', 1)} tags.
    Situation/Environment: exactly {tag_config.get('situation_environment', 1)} tags.
    Components: exactly {tag_config.get('components', 1)} tags.
    Time Period: exactly {tag_config.get('time_period', 1)} tag.

    Return the tags as a single, comma-separated string, with each tag enclosed in square brackets.
    The format MUST be: [Primary Genre],[Sub-genre1],[Sub-genre2],...
    Do not add any other text, explanations, or headings to your response.

    Track Details:
    Artist: {track_data.get('artist')}
    Title: {track_data.get('title')}
    Genre: {track_data.get('genre')}
    Grouping: {track_data.get('grouping')}
    Comments: {track_data.get('comments')}
    """

    client = openai.OpenAI()
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        # Extract the tag string and remove any whitespace
        tags_string = response.choices[0].message.content.strip()
        return tags_string
    except Exception as e:
        print(f"Error calling LLM: {e}")
        return None


def generate_rekordbox_xml(tracks, output_file_path):
    """
    Generates a new Rekordbox XML file with updated tags.
    """
    # Create the root element
    root = ET.Element('DJ_PLAYLISTS', version='1.0.0')

    # Add the product and settings elements
    product = ET.SubElement(root, 'PRODUCT', Name='rekordbox', Version='6.7.7')
    settings = ET.SubElement(root, 'SETTINGS')

    # Add the collection with all tracks
    collection = ET.SubElement(root, 'COLLECTION', Entries=str(len(tracks)))

    for track_data in tracks:
        track = ET.SubElement(collection, 'TRACK')
        track.set('Name', track_data['title'] if track_data['title'] is not None else '')
        track.set('Artist', track_data['artist'] if track_data['artist'] is not None else '')
        track.set('TrackID', track_data['track_id'] if track_data['track_id'] is not None else '')
        track.set('Location', track_data['id'] if track_data['id'] is not None else '')

        # Add original attributes
        if track_data['genre'] is not None:
            track.set('Genre', track_data['genre'])
        if track_data['comments'] is not None:
            track.set('Comments', track_data['comments'])

        # Add the generated tags to the Grouping field
        if track_data['llm_tags'] is not None:
            # Append the original grouping data to the comments for backup
            if track_data['grouping'] is not None and track_data['grouping'] != '':
                track.set('Comments', f"{track_data['comments']} | ORIGINAL_GROUPING: {track_data['grouping']}")

            # Put the new tags in the Grouping field
            track.set('Grouping', track_data['llm_tags'])

    tree = ET.ElementTree(root)
    ET.indent(tree, space="\t", level=0)
    tree.write(output_file_path, encoding='utf-8', xml_declaration=True)


# --- Flask Endpoints ---

@app.route('/upload_library', methods=['POST'])
def upload_library():
    """
    Receives an XML file, processes it, and stores it in the database.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    if 'config' not in request.form:
        return jsonify({'error': 'No configuration data in the request'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    config_json = request.form.get('config')
    tag_config = json.loads(config_json)

    try:
        xml_content = file.read()
        tracks = parse_rekordbox_xml(xml_content)

        conn = get_db_connection()
        for track in tracks:
            # Store the original tags in case we need to clear them later
            track_id = track.get('id')
            llm_tags = call_llm_for_tags(track, tag_config)

            conn.execute('''
                INSERT OR REPLACE INTO tracks (id, artist, title, track_id, genre, comments, grouping, llm_tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                track_id,
                track.get('artist'),
                track.get('title'),
                track.get('track_id'),
                track.get('genre'),
                track.get('comments'),
                track.get('grouping'),
                llm_tags
            ))
        conn.commit()
        conn.close()

        return jsonify({'message': 'Library uploaded and processed successfully!'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/export_xml', methods=['GET'])
def export_xml():
    """
    Generates a new XML file with the LLM tags and sends it for download.
    """
    try:
        conn = get_db_connection()
        cursor = conn.execute('SELECT * FROM tracks')
        tracks = cursor.fetchall()
        conn.close()

        if not tracks:
            return jsonify({'error': 'No tracks found in the database. Please upload a library first.'}), 404

        output_file_path = "tagged_library.xml"
        generate_rekordbox_xml(tracks, output_file_path)

        return send_file(output_file_path, as_attachment=True)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/clear_tags', methods=['PUT'])
def clear_tags():
    """
    Clears all generated tags from the database.
    """
    try:
        conn = get_db_connection()
        conn.execute('UPDATE tracks SET llm_tags = NULL')
        conn.commit()
        conn.close()
        return jsonify({'message': 'Generated tags have been cleared successfully.'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
