import os
import json
import sqlite3
import google.generativeai as genai
from flask import Flask, request, jsonify, render_template, redirect, url_for

app = Flask(__name__)

# ==========================================
# 👇 PASTE YOUR GOOGLE API KEY HERE!
# ==========================================
API_KEY = os.environ.get("GOOGLE_API_KEY")

genai.configure(api_key=API_KEY)
# Using the standard model
model = genai.GenerativeModel("models/gemini-1.5-flash")

UPLOAD_FOLDER = 'received_audio'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- Database Setup (YOUR ORIGINAL CODE) ---
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

# --- 🧠 THE NEW PRIVACY FILTER FUNCTION ---
def process_with_privacy_check(user_text):
    """
    Asks Gemini: Is this a complaint (Save it) or a Call (Ignore it)?
    """
    prompt = f"""
    Analyze this resident input: "{user_text}"
    
    Rules:
    1. If the user wants to CALL or MESSAGE (e.g., "Call 101", "Phone lagao", "Connect me"), output JSON:
       {{"intent": "private", "action": "call", "target": "101", "text": "Calling 101", "category": "Private"}}

    2. If it is a COMPLAINT (e.g., "Tap leaking", "Lift stuck", "Pani nahi hai"), output JSON:
       {{"intent": "complaint", "category": "Maintenance", "text": "Issue detected: {user_text}", "action": "none", "target": "none"}}
       (Categories: Plumbing, Electrical, Security, Cleaning, General).

    Output ONLY raw JSON. No markdown.
    """
    
    try:
        response = model.generate_content(prompt)
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_text)
        
        # 🚦 THE CHECK: Only save if it is a complaint
        if data.get('intent') == 'complaint':
            conn = sqlite3.connect('apartment.db')
            c = conn.cursor()
            c.execute("INSERT INTO tickets (category, description, status) VALUES (?, ?, ?)",
                      (data['category'], data['text'], 'Open'))
            conn.commit()
            conn.close()
            print(f"✅ Ticket Saved: {data['text']}")
        else:
            print(f"🔒 Private Action (Not Saved): {data['text']}")
            
        return data

    except Exception as e:
        print(f"AI Error: {e}")
        return {"intent": "complaint", "category": "General", "text": user_text} # Fallback

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
    
    try:
        myfile = genai.upload_file(file_path)
        
        # Ask Gemini to transcode AND analyze in one step
        prompt = """
        Listen to this audio.
        If it is a command to Call/Message, output JSON with intent='private'.
        If it is a Complaint, output JSON with intent='complaint'.
        Output ONLY valid JSON: { "intent": "...", "category": "...", "text": "...", "action": "...", "target": "..." }
        """
        
        result = model.generate_content([myfile, prompt])
        clean_text = result.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_text)

        # 🚦 PRIVACY CHECK FOR AUDIO
        if data.get('intent') == 'complaint':
            conn = sqlite3.connect('apartment.db')
            c = conn.cursor()
            c.execute("INSERT INTO tickets (category, description, status) VALUES (?, ?, ?)",
                      (data['category'], data['text'], 'Open'))
            conn.commit()
            conn.close()

        return jsonify({
            "message": "Processed", 
            "ai_response": json.dumps(data), # Send JSON string to App
            "status": "success"
        })

    except Exception as e:
        return jsonify({"message": f"AI Error: {e}", "status": "error"}), 500

# --- Handle Text Commands ---
@app.route('/upload_text', methods=['POST'])
def upload_text():
    data = request.json
    user_text = data.get('text', '')
    
    # Use the new privacy function
    ai_data = process_with_privacy_check(user_text)

    return jsonify({
        "message": "Processed", 
        "ai_response": json.dumps(ai_data), # Send JSON string to App
        "status": "success"
    })

# --- View Dashboard (YOUR ORIGINAL CODE) ---
@app.route('/dashboard')
def view_dashboard():
    conn = sqlite3.connect('apartment.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM tickets ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return render_template('dashboard.html', tickets=rows)

# --- Resolve Ticket (YOUR ORIGINAL CODE) ---
@app.route('/resolve/<int:ticket_id>', methods=['POST'])
def resolve_ticket(ticket_id):
    conn = sqlite3.connect('apartment.db')
    c = conn.cursor()
    c.execute("UPDATE tickets SET status = 'Resolved' WHERE id = ?", (ticket_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('view_dashboard'))

# --- API for JSON Data (YOUR ORIGINAL CODE) ---
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
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)