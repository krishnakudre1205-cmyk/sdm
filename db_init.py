# db_init.py
import sqlite3, os
import bcrypt
from dotenv import load_dotenv

load_dotenv()

# Database file
DB = os.getenv('DATABASE_URL', 'data.db')

def create_tables():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    # Create tables
    cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT,
        role TEXT,
        email TEXT,
        phone TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        module TEXT,
        data TEXT,
        status TEXT DEFAULT 'pending',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        flagged INTEGER DEFAULT 0
    )
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message TEXT,
        target_user TEXT,
        sent INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        token TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    con.commit()
    con.close()
    print("Tables created successfully in", DB)

def add_user(username, password, role, email='', phone=''):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    phash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    try:
        cur.execute(
            "INSERT INTO users (username, password_hash, role, email, phone) VALUES (?,?,?,?,?)",
            (username, phash, role, email, phone)
        )
        con.commit()
        print("Seeded user:", username)
    except sqlite3.IntegrityError:
        print("Seed skipped (already exists):", username)
    except Exception as e:
        print("Error seeding user:", username, e)
    finally:
        con.close()

if __name__ == "__main__":
    create_tables()
    # Seed initial users
    add_user('admin', '1234', 'supervisor', 'supervisor@example.com', '')
    add_user('asha1', '100', 'asha', 'asha01@example.com', '')
    print("DB initialization complete.")
