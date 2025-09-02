import sqlite3
from flask import Flask, jsonify

app = Flask(__name__)

'''
Create a new connection to database every time function is called.
'''


def get_db_connection():
    conn = sqlite3.connect('music_theory.db')
    conn.row_factory = sqlite3.Row  # Allows for data access by column instead of just index.
    return conn


@app.route('/')
def hello_ai():
    return 'Hello, Ai!'


@app.route('/concepts', methods=['GET'])
def get_concepts():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if the "Major Scale" concept already exists
    cursor.execute("SELECT * FROM concepts WHERE name=?", ('Major Scale',))
    existing_concept = cursor.fetchone()

    # If the concept does not exist, insert it
    if not existing_concept:
        cursor.execute("INSERT INTO concepts (name, description) VALUES (?, ?)",
                       ('Major Scale', 'A major scale is a diatonic scale consisting of seven notes.')) # I might consider linking or elaborating on extra jargon
        conn.commit()

    # Query all concepts from the database
    concepts = conn.execute('SELECT * FROM concepts').fetchall()
    conn.close()

    # Convert the list of rows into a list of dictionaries for JSON serialization
    concepts_list = [dict(row) for row in concepts]

    return jsonify(concepts_list)

if __name__ == '__main__':
    app.run(debug=True)