import os
import json
import sqlite3
import google.generativeai as genai
from flask import Flask, request, jsonify, render_template, redirect, url_for

app = Flask(__name__)

# ==========================================
# 👇 API KEY & MODEL SETUP
# ==========================================
API_KEY = os.environ.get("GOOGLE_API_KEY")
genai.configure(api_key=API_KEY)

# ✅ RESTORED THE WORKING MODEL NAME
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

# --- 🧠 FORCE PRIVACY LOGIC ---
def strict_privacy_check(text):
    text_lower = text.lower()
    
    # 1. HARD RULE: If these words exist, it is 100% PRIVATE.
    # We do NOT ask the AI's opinion for these to avoid mistakes.
    private_keywords = ["call", "phone", "message", "contact", "connect", "ring", "talk to"]
    
    for word in private_keywords:
        if word in text_lower:
            # Extract target (simple logic: look for numbers like '101')
            target = ''.join(filter(str.isdigit, text)) or "Security"
            return {
                "intent": "private",
                "action": "call" if "mess" not in text_lower else "message",
                "target": target,
                "text": text,
                "category": "Private"
            }

    # 2. If no keywords, ask AI to classify the complaint
    prompt = f"""
    Analyze this complaint: "{text}"
    Output valid JSON: {{"intent": "complaint", "category": "Maintenance", "text": "Issue: {text}"}}
    Categories: Plumbing, Electrical, Security, Cleaning.
    """
    try:
        response = model.generate_content(prompt)
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except:
        # Fallback to complaint if AI fails
        return {"intent": "complaint", "category": "General", "text": text}

@app.route('/')
def home():
    return "Server Running (Model: models/gemini-flash-latest)"

# --- AUDIO HANDLER ---
@app.route('/upload_audio', methods=['POST'])
def upload_audio():
    if 'audio' not in request.files:
        return jsonify({"message": "No audio file", "status": "error"}), 400
    
    audio_file = request.files['audio']
    file_path = os.path.join(UPLOAD_FOLDER, "command.m4a")
    audio_file.save(file_path)
    
    try:
        # 1. Transcribe Audio ONLY
        myfile = genai.upload_file(file_path)
        transcribe_prompt = "Transcribe this audio exactly into English text. Output ONLY the text."
        
        result = model.generate_content([myfile, transcribe_prompt])
        transcribed_text = result.text.strip()
        
        print(f"🎤 Heard: {transcribed_text}")

        # 2. Run Strict Privacy Check
        ai_data = strict_privacy_check(transcribed_text)
        
        # 3. Save ONLY if Complaint
        if ai_data.get('intent') == 'complaint':
            conn = sqlite3.connect('apartment.db')
            c = conn.cursor()
            c.execute("INSERT INTO tickets (category, description, status) VALUES (?, ?, ?)",
                      (ai_data.get('category', 'General'), ai_data.get('text'), 'Open'))
            conn.commit()
            conn.close()
            print("✅ Ticket Saved")
        else:
            print("🔒 Private Call Detected - DB Skipped")

        return jsonify({
            "message": "Processed", 
            "ai_response": json.dumps(ai_data),
            "status": "success"
        })

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"message": f"Server Error: {e}", "status": "error"}), 500

# --- TEXT HANDLER ---
@app.route('/upload_text', methods=['POST'])
def upload_text():
    data = request.json
    user_text = data.get('text', '')
    
    # Run Strict Privacy Check
    ai_data = strict_privacy_check(user_text)

    if ai_data.get('intent') == 'complaint':
        conn = sqlite3.connect('apartment.db')
        c = conn.cursor()
        c.execute("INSERT INTO tickets (category, description, status) VALUES (?, ?, ?)",
                  (ai_data.get('category', 'General'), ai_data.get('text'), 'Open'))
        conn.commit()
        conn.close()

    return jsonify({
        "message": "Processed", 
        "ai_response": json.dumps(ai_data), 
        "status": "success"
    })

# --- Dashboard & Tickets ---
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
    tickets = [dict(row) for row in rows]
    conn.close()
    return jsonify(tickets)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)