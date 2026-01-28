import os
import json
import sqlite3
import google.generativeai as genai
from flask import Flask, request, jsonify, render_template, redirect, url_for

app = Flask(__name__)

# ==========================================
# 👇 API KEY SETUP
# ==========================================
API_KEY = os.environ.get("GOOGLE_API_KEY")
genai.configure(api_key=API_KEY)
# Using your working model
model = genai.GenerativeModel("models/gemini-flash-latest")

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

# --- 🧠 THE AI BRAIN (Privacy Logic) ---
def analyze_intent_and_process(text):
    prompt = f"""
    You are a Society AI Security System. Analyze this input: "{text}"
    
    CRITICAL RULES:
    1. IF the input contains "call", "message", "phone", "contact", "connect", "talk to", "ring", or mentions a flat number for connection (e.g. "Call 101", "Message 202"):
       -> YOU MUST classify this as "private".
       -> Output JSON: {{"intent": "private", "action": "call", "target": "101", "text": "Calling 101", "category": "Private"}}

    2. IF the input is about a broken item, maintenance, water, electricity, lift, or danger:
       -> Classify as "complaint".
       -> Output JSON: {{"intent": "complaint", "category": "Maintenance", "text": "Issue detected: {text}", "action": "none", "target": "none"}}

    3. If unsure, default to "complaint".

    Output ONLY raw JSON. No markdown.
    """
    
    try:
        response = model.generate_content(prompt)
        cleaned_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_text)
    except Exception as e:
        print(f"AI Error: {e}")
        return {"intent": "complaint", "category": "General", "text": text}

@app.route('/')
def home():
    return "The Server is Alive!"

# --- Handle Text Commands ---
@app.route('/upload_text', methods=['POST'])
def upload_text():
    data = request.json
    if not data or 'text' not in data:
        return jsonify({"message": "No text provided", "status": "error"}), 400
    
    user_text = data['text']
    print(f"📩 Received Text: {user_text}")

    try:
        # 1. Analyze Intent
        ai_data = analyze_intent_and_process(user_text)
        print(f"🤖 AI Analysis: {ai_data}")
        
        # 2. PRIVACY CHECK (The Gatekeeper)
        if ai_data.get('intent') == 'complaint':
            # ✅ Save Complaint
            conn = sqlite3.connect('apartment.db')
            c = conn.cursor()
            c.execute("INSERT INTO tickets (category, description, status) VALUES (?, ?, ?)",
                      (ai_data['category'], ai_data['text'], 'Open'))
            conn.commit()
            conn.close()
            print("✅ Ticket Saved")
        else:
            # 🛑 Private Action (Ignored)
            print(f"🔒 Private Action Detected ({user_text}) - NOT SAVED to DB")

        return jsonify({
            "message": "Processed", 
            "ai_response": json.dumps(ai_data), 
            "status": "success"
        })

    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({"message": f"Server Error: {e}", "status": "error"}), 500

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
        prompt = """
        Listen to this audio.
        1. If user says "Call", "Message", "Phone", classify as intent='private'.
        2. If user reports an issue (water, lift, broken), classify as intent='complaint'.
        Output ONLY valid JSON: { "intent": "...", "category": "...", "text": "...", "action": "...", "target": "..." }
        """
        
        result = model.generate_content([myfile, prompt])
        clean_text = result.text.replace("```json", "").replace("```", "").strip()
        ai_data = json.loads(clean_text)
        
        if ai_data.get('intent') == 'complaint':
            conn = sqlite3.connect('apartment.db')
            c = conn.cursor()
            c.execute("INSERT INTO tickets (category, description, status) VALUES (?, ?, ?)",
                      (ai_data['category'], ai_data['text'], 'Open'))
            conn.commit()
            conn.close()

        return jsonify({
            "message": "Processed", 
            "ai_response": json.dumps(ai_data),
            "status": "success"
        })

    except Exception as e:
        return jsonify({"message": f"AI Error: {e}", "status": "error"}), 500

# --- Dashboard & API ---
@app.route('/dashboard')
def view_dashboard():
    conn = sqlite3.connect('apartment.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM tickets ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return render_template('dashboard.html', tickets=rows)

@app.route('/resolve/<int:ticket_id>', methods=['POST'])
def resolve_ticket(ticket_id):
    conn = sqlite3.connect('apartment.db')
    c = conn.cursor()
    c.execute("UPDATE tickets SET status = 'Resolved' WHERE id = ?", (ticket_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('view_dashboard'))

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