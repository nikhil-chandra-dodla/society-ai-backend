import os
import json
import sqlite3
import google.generativeai as genai
from flask import Flask, request, jsonify, render_template, redirect, url_for

app = Flask(__name__)

# ==========================================
# 👇 PASTE YOUR GOOGLE API KEY HERE!
# ==========================================
# (On Render, this pulls from the Environment Variable automatically)
API_KEY = os.environ.get("GOOGLE_API_KEY")

genai.configure(api_key=API_KEY)
# Using the stable Flash model
model = genai.GenerativeModel("models/gemini-1.5-flash")

UPLOAD_FOLDER = 'received_audio'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect('apartment.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tickets
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  category TEXT,
                  description TEXT,
                  status TEXT,
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    return "The Server is Alive!"

# --- Handle Voice Commands ---
@app.route('/upload_audio', methods=['POST'])
def upload_audio():
    if 'audio' not in request.files:
        return jsonify({"message": "No audio file", "status": "error"}), 400
    
    audio_file = request.files['audio']
    file_path = os.path.join(UPLOAD_FOLDER, "command.m4a")
    audio_file.save(file_path)
    
    print(f"🎤 Audio saved. Sending to Gemini...")

    try:
        myfile = genai.upload_file(file_path)
        
        # 👇 NEW STRICT PROMPT: Forces English Output & Better Categories
        prompt = """
        Listen to this audio. The user may speak in English, Hindi, or Telugu.
        Your task is to TRANSLATE everything into clear ENGLISH.
        
        Return a strict JSON response with these two fields:
        1. 'text': The English translation of what was said.
        2. 'category': Classify it as one of [Plumbing, Electrical, Security, Cleaning, General].
        """
        
        result = model.generate_content([myfile, prompt])
        
        clean_text = result.text.replace("```json", "").replace("```", "").strip()
        print(f"🤖 Gemini says: {clean_text}")
        
        # Save to DB
        data = json.loads(clean_text) 
        conn = sqlite3.connect('apartment.db')
        c = conn.cursor()
        c.execute("INSERT INTO tickets (category, description, status) VALUES (?, ?, ?)",
                  (data['category'], data['text'], 'Open'))
        conn.commit()
        conn.close()

        return jsonify({
            "message": "Processed and Saved", 
            "ai_response": clean_text,
            "status": "success"
        })

    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({"message": f"AI Error: {e}", "status": "error"}), 500

# --- View Dashboard ---
@app.route('/dashboard')
def view_dashboard():
    conn = sqlite3.connect('apartment.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM tickets ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return render_template('dashboard.html', tickets=rows)

# --- Resolve Ticket (Mark Done) ---
@app.route('/resolve/<int:ticket_id>', methods=['POST'])
def resolve_ticket(ticket_id):
    conn = sqlite3.connect('apartment.db')
    c = conn.cursor()
    # Update the status in the database
    c.execute("UPDATE tickets SET status = 'Resolved' WHERE id = ?", (ticket_id,))
    conn.commit()
    conn.close()
    # Refresh the dashboard page
    return redirect(url_for('view_dashboard'))

# --- API for JSON Data ---
@app.route('/tickets', methods=['GET'])
def get_tickets():
    conn = sqlite3.connect('apartment.db')
    conn.row_factory = sqlite3.Row 
    c = conn.cursor()
    c.execute("SELECT * FROM tickets ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    
    tickets = []
    for row in rows:
        tickets.append(dict(row))
    return jsonify(tickets)

if __name__ == '__main__':
    # The Cloud sets an environment variable called 'PORT'
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)