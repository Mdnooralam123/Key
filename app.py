# app.py — Final Boss (Fast JSON + Redis Fallback + All Errors Fixed)
import os
import json
import hashlib
import time
import secrets
import string
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify

app = Flask(__name__)

KEY_PREFIX = "KHAN"
DAY_SECONDS = 86400
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "keys.json")

# ---------- Settings ----------
GENERATE_API_KEY = os.environ.get("GENERATE_API_KEY", "khan123").strip()
ON_VERCEL = bool(os.environ.get("VERCEL"))
_memory_db = {} # Vercel ke liye temporary memory

# ---------- Fast In-Memory Cache for keys.json ----------
_cache = {"mtime": None, "data": {}}

def load_json():
    if not os.path.exists(DATA_FILE): return {}
    try:
        mtime = os.path.getmtime(DATA_FILE)
        if _cache["mtime"] == mtime:
            return _cache["data"]
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _cache["mtime"] = mtime
        _cache["data"] = data
        return data
    except: return {}

def save_json(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    _cache["mtime"] = None
    _cache["data"] = {}

# ---------- Unified Storage (JSON for Local, Memory for Vercel) ----------
def storage_get(key):
    if ON_VERCEL:
        return _memory_db.get(key)
    return load_json().get(key)

def storage_save(key, data):
    if ON_VERCEL:
        _memory_db[key] = data
    else:
        allk = load_json()
        allk[key] = data
        save_json(allk)

# ---------- Helper Functions ----------
def now_utc(): return datetime.now(timezone.utc)
def iso(dt): return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def parse_iso(s):
    try: return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except: return None
def is_true(v): return str(v).lower() in ("1", "true", "yes")

def format_remaining(sec):
    if sec <= 0: return "0s"
    d, rem = divmod(sec, DAY_SECONDS)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s or not parts: parts.append(f"{s}s")
    return " ".join(parts)

def normalize_type(raw):
    if not raw: return None
    v = raw.strip().lower()
    if v in ("1", "1day", "1d"): return "1day"
    if v in ("7", "7days", "7d"): return "7days"
    if v in ("30", "30days", "30d"): return "30days"
    if v in ("life", "lifetime", "forever", "inf"): return "lifetime"
    return None

def make_block():
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(4))

def device_fp():
    ua = request.headers.get("User-Agent", "")
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    return hashlib.sha256(f"{ua}|{ip}".encode()).hexdigest()[:32]


# ---------- ROUTES ----------
@app.route("/")
def home():
    return jsonify({
        "status": "success",
        "message": "Welcome to KHAN Key Generator API",
        "endpoints": {
            "generate": "/generate?type=lifetime&api_key=khan123",
            "check": "/check?key=KHAN-XXXX-XXXX-XXXX"
        }
    })

@app.route("/generate", methods=["GET", "POST"])
def generate():
    body = request.get_json(silent=True) if request.method == "POST" else request.args
    
    # API Key Security
    api_key = (body.get("api_key") or request.headers.get("X-API-Key") or "").strip()
    if api_key != GENERATE_API_KEY:
        return jsonify({"status": "error", "message": "Unauthorized! Add ?api_key=khan123"}), 401

    ktype = normalize_type(body.get("type") or body.get("plan") or "")
    if not ktype:
        return jsonify({"status": "error", "message": "Invalid type. Use 1day, 7days, 30days, lifetime."}), 400

    key = f"{KEY_PREFIX}-{make_block()}-{make_block()}-{make_block()}"
    created = now_utc()

    if ktype == "lifetime":
        expires_str, validity, lifetime = None, "Lifetime", True
    else:
        days = 1 if ktype == "1day" else (7 if ktype == "7days" else 30)
        expires = created + timedelta(days=days)
        expires_str, validity, lifetime = iso(expires), f"{days} Days", False

    record = {
        "key": key, "type": ktype, "validity": validity, "created_at": iso(created),
        "expires_at": expires_str, "lifetime": "1" if lifetime else "0",
        "bound_fingerprint": "", "device_ip": "", "device_ua": ""
    }

    # Save Data
    try:
        storage_save(key, record)
    except Exception as e:
        return jsonify({"status": "error", "message": "Save failed. Storage error."}), 500

    response = {
        "status": "success", "key": key, "type": ktype, "validity": validity,
        "expires_at": expires_str, "lifetime": lifetime, "message": "Key generate & save ho gayi!"
    }
    if ON_VERCEL:
        response["warning"] = "Vercel Memory Mode: Key restart par delete ho jayegi."
    return jsonify(response)

@app.route("/check", methods=["GET", "POST"])
def check():
    body = request.get_json(silent=True) if request.method == "POST" else request.args
    key = (body.get("key") or "").strip().upper()
    if not key: return jsonify({"status": "error", "message": "Provide ?key=..."}), 400

    # Fast check from JSON/Memory
    data = storage_get(key)
    
    if not data:
        return jsonify({
            "status": "success", "real": False, "valid": False, 
            "message": "❌ Ye key fake hai ya exist nahi karti."
        })

    now = now_utc()
    lifetime = is_true(data.get("lifetime"))
    fp = device_fp()
    bound_fp = data.get("bound_fingerprint") or ""

    # Device Lock
    if not bound_fp:
        data["bound_fingerprint"] = fp
        data["device_ip"] = request.remote_addr
        data["device_ua"] = request.headers.get("User-Agent", "")[:100]
        storage_save(key, data)
        dev_msg = "🔒 Key is device par lock ho gayi."
    elif bound_fp == fp:
        dev_msg = "✅ Key isi device par active hai."
    else:
        return jsonify({
            "status": "success", "real": True, "valid": False, "device_mismatch": True,
            "message": "🚫 Ye key dusre device par locked hai!"
        })

    if lifetime:
        return jsonify({
            "status": "success", "real": True, "valid": True, "expired": False,
            "type": "lifetime", "remaining": "Lifetime", "message": dev_msg
        })

    expires = parse_iso(data.get("expires_at") or "")
    remaining = int((expires - now).total_seconds()) if expires else 0

    if remaining <= 0:
        return jsonify({
            "status": "success", "real": True, "valid": False, "expired": True,
            "remaining": "0s", "message": "⏰ Key expire ho chuki hai."
        })

    return jsonify({
        "status": "success", "real": True, "valid": True, "expired": False,
        "remaining": format_remaining(remaining), "message": dev_msg
    })

@app.errorhandler(404)
def not_found(e):
    return jsonify({"status": "error", "message": "Route not found. Check URL."}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"status": "error", "message": "Internal server error."}), 500

if __name__ == "__main__":
    if not os.path.exists(DATA_FILE): save_json({})
    app.run(host="0.0.0.0", port=5000)