# server.py
import os
import subprocess
import sys
import sqlite3
from flask import Flask, request, jsonify, send_from_directory
from datetime import datetime

# ── Ensure Flask and Werkzeug are installed ──────────────────────────────────
subprocess.run([sys.executable, "-m", "pip", "install", "flask", "werkzeug"], check=True)

from werkzeug.security import generate_password_hash, check_password_hash

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_FILE   = os.path.join(BASE_DIR, 'hiver.db')
MEDIA_DIR = os.path.join(BASE_DIR, 'media')

# ── App & DB Setup ───────────────────────────────────────────────────────────
app = Flask(__name__)
os.makedirs(MEDIA_DIR, exist_ok=True)

conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()

# ── Tables ───────────────────────────────────────────────────────────────────
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash TEXT
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS chats (
    chat_id TEXT PRIMARY KEY,
    created_at TEXT
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT,
    sender TEXT,
    text TEXT,
    timestamp TEXT,
    media_path TEXT,
    FOREIGN KEY(chat_id) REFERENCES chats(chat_id)
)
""")
conn.commit()

# ── Authentication Endpoints ─────────────────────────────────────────────────
@app.route('/register', methods=['POST'])
def register():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'error': 'Missing username or password'}), 400
    c.execute("SELECT 1 FROM users WHERE username = ?", (username,))
    if c.fetchone():
        return jsonify({'error': 'User already exists'}), 400
    pw_hash = generate_password_hash(password)
    c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, pw_hash))
    conn.commit()
    return jsonify({'status': 'Registered'}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'error': 'Missing username or password'}), 400
    c.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    if row and check_password_hash(row[0], password):
        return jsonify({'status': 'Logged in'}), 200
    return jsonify({'error': 'Invalid credentials'}), 401

# ── Chat Endpoints ────────────────────────────────────────────────────────────
@app.route('/chats', methods=['GET'])
def list_chats():
    c.execute("SELECT chat_id FROM chats")
    return jsonify({'chats': [r[0] for r in c.fetchall()]})

@app.route('/create_chat', methods=['POST'])
def create_chat():
    chat_id = (request.json or {}).get('chat_id')
    if not chat_id:
        return jsonify({'error': 'Missing chat_id'}), 400
    c.execute("SELECT 1 FROM chats WHERE chat_id = ?", (chat_id,))
    if c.fetchone():
        return jsonify({'error': 'Chat already exists'}), 400
    c.execute(
        "INSERT INTO chats (chat_id, created_at) VALUES (?, ?)",
        (chat_id, datetime.utcnow().isoformat())
    )
    conn.commit()
    return jsonify({'status': 'Chat created'}), 201

@app.route('/delete_chat', methods=['POST'])
def delete_chat():
    chat_id = (request.json or {}).get('chat_id')
    c.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
    c.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
    conn.commit()
    # Remove media directory for that chat
    path = os.path.join(MEDIA_DIR, chat_id)
    if os.path.isdir(path):
        for f in os.listdir(path):
            os.remove(os.path.join(path, f))
        os.rmdir(path)
    return jsonify({'status': 'Chat deleted'})

@app.route('/send_message', methods=['POST'])
def send_message():
    chat_id = request.form.get('chat_id')
    sender = request.form.get('sender')
    text = request.form.get('text', '')
    media_path = None
    if 'file' in request.files:
        f = request.files['file']
        chat_dir = os.path.join(MEDIA_DIR, chat_id)
        os.makedirs(chat_dir, exist_ok=True)
        media_path = os.path.join(chat_dir, f.filename)
        f.save(media_path)
    c.execute(
        "INSERT INTO messages (chat_id, sender, text, timestamp, media_path) VALUES (?, ?, ?, ?, ?)",
        (chat_id, sender, text, datetime.utcnow().isoformat(), media_path)
    )
    conn.commit()
    return jsonify({'status': 'Message sent'})

@app.route('/get_messages', methods=['GET'])
def get_messages():
    chat_id = request.args.get('chat_id')
    c.execute(
        "SELECT sender, text, timestamp, media_path FROM messages WHERE chat_id = ? ORDER BY id",
        (chat_id,)
    )
    messages = []
    for sender, text, ts, media in c.fetchall():
        media_info = {'url': f"/media/{chat_id}/{os.path.basename(media)}"} if media else None
        messages.append({'sender': sender, 'text': text, 'timestamp': ts, 'media': media_info})
    return jsonify({'messages': messages})

@app.route('/media/<chat_id>/<filename>')
def serve_media(chat_id, filename):
    return send_from_directory(os.path.join(MEDIA_DIR, chat_id), filename)

if __name__ == '__main__':
    app.run(port=5000)
