# app.py — 100% Error Free Version
import os
import json
import hashlib
import time
import secrets
import string
import requests
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify

app = Flask(__name__)

KEY_PREFIX = "KHAN"
DAY_SECONDS = 86400
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "keys.json")

# API Key to protect /generate (Default: khan123)
GENERATE_API_KEY = os.environ.get("GENERATE_API_KEY", "khan123").strip()

# Upstash Redis Setup (Optional but recommended for Vercel)
REDIS_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "").strip()
REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip()
USE_REDIS = bool(REDIS_URL and REDIS_TOKEN)
ON_VERCEL = bool(os.environ.get("VERCEL"))

# Temporary memory (Agar Vercel par Redis nahi hai, toh yahan save hoga taaki error na aaye)
_memory_db = {}

# ---------- Upstash Helper ----------
def redis_command(*args):
    if not USE_REDIS: return None
    headers = {"Authorization": f"Bearer {REDIS_TOKEN}", "Content-Type": "application/json"}
    try:
        res = requests.post(REDIS_URL, headers=headers, json=list(args), timeout=5)
        res.raise_for_status()
        return res.json().get("result")
    except Exception as e:
        return None

# ---------- Storage System ----------
def _load_json():
    if not os.path.exists(DATA_FILE): return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def _save_json(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)

def storage_get(key):
    if USE_REDIS:
        res = redis_command("HGETALL", f"key:{key}")
        return dict(zip(res[::2], res[1::2])) if res else None
    elif ON_VERCEL:
        return _memory_db.get(key)
    return _load_json().get(key)

def storage_save(key, data):
    if USE_REDIS:
        args = ["HSET", f"key:{key}"]
        for k, v in data.items():
            args.extend([k, "" if v is None else str(v)])
        res = redis_command(*args)
        if res is None: raise Exception("Redis Save Failed")
    elif ON_VERCEL:
        _memory_db[key] = data # Temporary save in RAM
    else:
        allk = _load_json()
        allk[key] = data
        _save_json(allk)

# ---------- Generic Helpers ----------
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
@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({"status": "error", "message": str(e), "type": type(e).__name__}), 500

@app.route("/generate", methods=["GET", "POST"])
def generate():
    body = request.get_json(silent=True) if request.method == "POST" else request.args
    
    # 1. Check API Key
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

    # 2. Save Key (Agar fail hua toh key generate nahi hogi)
    try:
        storage_save(key, record)
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Key generate nahi ho payi kyunki storage full/error hai.",
            "error": str(e)
        }), 500

    response = {
        "status": "success", "key": key, "type": ktype, "validity": validity,
        "expires_at": expires_str, "lifetime": lifetime, "message": "Key successfully generate aur save ho gayi!"
    }
    
    if ON_VERCEL and not USE_REDIS:
        response["warning"] = "⚠️ Ye key temporary memory me save hui hai. Vercel restart hote hi delete ho jayegi. Permanent save ke liye Upstash Redis lagayein."

    return jsonify(response)

@app.route("/check", methods=["GET", "POST"])
def check():
    body = request.get_json(silent=True) if request.method == "POST" else request.args
    key = (body.get("key") or "").strip().upper()
    if not key: return jsonify({"status": "error", "message": "Provide ?key=..."}), 400

    data = storage_get(key)
    
    # Agar key nahi mili
    if not data:
        return jsonify({
            "status": "success", "real": False, "valid": False, 
            "message": "❌ Ye key database me nahi mili. Fake hai ya delete ho chuki hai."
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
        dev_msg = "🔒 Key pehli baar is device par lock ho gayi."
    elif bound_fp == fp:
        dev_msg = "✅ Key isi device par active hai."
    else:
        return jsonify({
            "status": "success", "real": True, "valid": False, "device_mismatch": True,
            "message": "🚫 Ye key kisi dusre device par locked hai!"
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)