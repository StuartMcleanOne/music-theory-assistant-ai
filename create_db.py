import sqlite3
import sys

def create_database():
    try:
        conn = sqlite3.connect('music_theory.db')
        cursor = conn.cursor()

        print("connection to database established. Creating tables...")


        # Create the concepts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS concepts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT
            )
        ''')

        # Create the lesson table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL, 
                content TEXT,
                concept_id INTEGER,
                FOREIGN KEY (concept_id) REFERENCES concepts (id)
            )
        ''')

        # Create the user_interactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_interactions (
                if INTEGER PRIMARY KEY AUTOINCREMENT,
                user_question TEXT NOT NULL,
                ai_response TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()
        print("Database and tables created sucessfully!")
    except sqlite3.Error as e:
        print(f"An error occurred: {e}", file=sys.stderr)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)

if __name__ =='__main__':
    create_database()