# app.py — Vercel Ready (Bulletproof)
import os
import json
import hashlib
import time
import secrets
import string
import requests
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, Response
from werkzeug.exceptions import HTTPException

app = Flask(__name__)

KEY_PREFIX = "KHAN"
DAY_SECONDS = 86400
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "keys.json")

# ---------- backend auto-detect ----------
REDIS_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "").strip()
REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip()
USE_REDIS = bool(REDIS_URL and REDIS_TOKEN)

ON_VERCEL = bool(os.environ.get("VERCEL"))
MODE = "redis" if USE_REDIS else "json"


# ---------- Global Error Handler (Vercel debug ke liye) ----------
@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return e
    return jsonify({
        "status": "error",
        "message": "Internal Server Error",
        "error_details": str(e),
        "type": type(e).__name__,
        "fix_tip": "Check your Vercel Environment Variables and logs."
    }), 500


# ---------- Upstash REST API Helpers (No SDK needed) ----------
def redis_command(*args):
    if not USE_REDIS:
        return None
    headers = {
        "Authorization": f"Bearer {REDIS_TOKEN}",
        "Content-Type": "application/json"
    }
    try:
        res = requests.post(REDIS_URL, headers=headers, json=list(args), timeout=5)
        res.raise_for_status()
        return res.json().get("result")
    except Exception as e:
        print(f"Redis Error: {e}")
        return None


# ---------- keys.json file helpers ----------
_fc = {"mtime": None, "data": {}}

def _load_json():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        mtime = os.path.getmtime(DATA_FILE)
        if _fc["mtime"] == mtime:
            return _fc["data"]
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
        _fc["mtime"] = mtime
        _fc["data"] = data
        return data
    except Exception:
        return {}

def _save_json(data):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, DATA_FILE)
    _fc["mtime"] = None
    _fc["data"] = {}


# ---------- unified storage API ----------
def storage_get(key):
    if USE_REDIS:
        res = redis_command("HGETALL", f"key:{key}")
        if not res:
            return None
        return dict(zip(res[::2], res[1::2]))
    return _load_json().get(key)

def storage_save(key, data):
    if USE_REDIS:
        args = ["HSET", f"key:{key}"]
        for k, v in data.items():
            args.extend([k, "" if v is None else str(v)])
        redis_command(*args)
    else:
        allk = _load_json()
        allk[key] = data
        _save_json(allk)

def storage_all():
    if USE_REDIS:
        out = {}
        keys = redis_command("KEYS", "key:*")
        if not keys:
            return out
        for k in keys:
            key_name = k.replace("key:", "")
            d = storage_get(key_name)
            if d:
                out[d.get("key") or key_name] = d
        return out
    return _load_json()

def storage_delete(key):
    if USE_REDIS:
        redis_command("DEL", f"key:{key}")
    else:
        allk = _load_json()
        if key in allk:
            del allk[key]
            _save_json(allk)


# ---------- generic helpers ----------
def now_utc():
    return datetime.now(timezone.utc)

def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_iso(s):
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None

def is_true(v):
    if v is None: return False
    if isinstance(v, bool): return v
    return str(v).lower() in ("1", "true", "yes")

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
    if v in ("30", "30days", "30d", "30day", "month", "monthly"): return "30days"
    if v in ("life", "lifetime", "forever", "unlimited", "inf"): return "lifetime"
    return None

def make_block():
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(4))

def make_new_key():
    for _ in range(20):
        key = f"{KEY_PREFIX}-{make_block()}-{make_block()}-{make_block()}"
        if not storage_get(key):
            return key
    return f"{KEY_PREFIX}-{int(time.time()*1000)}{make_block()}"


# ---------- device fingerprint ----------
def device_fp():
    ua = request.headers.get("User-Agent", "")
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    lang = request.headers.get("Accept-Language", "")
    return hashlib.sha256(f"{ua}|{ip}|{lang}".encode()).hexdigest()[:32]

def device_info():
    return {
        "user_agent": request.headers.get("User-Agent", "Unknown")[:180],
        "ip": request.headers.get("X-Forwarded-For", request.remote_addr or "Unknown").split(",")[0].strip(),
        "language": request.headers.get("Accept-Language", "Unknown")[:60],
        "fingerprint": device_fp(),
    }


# ---------- routes ----------
@app.route("/")
def home():
    return jsonify({
        "status": "success",
        "app": "KHAN Key Generator",
        "storage_mode": MODE,
        "storage_location": "Upstash Redis REST" if USE_REDIS else DATA_FILE,
        "endpoints": {
            "generate_30days": "/generate?type=30days",
            "generate_lifetime": "/generate?type=lifetime",
            "check": "/check?key=KHAN-XXXX-XXXX-XXXX",
            "list": "/list",
            "export": "/export"
        }
    })

@app.route("/generate", methods=["GET", "POST"])
def generate():
    body = request.get_json(silent=True) if request.method == "POST" else request.args
    raw = (body.get("type") or body.get("plan") or "")
    ktype = normalize_type(raw)

    if not ktype:
        return jsonify({"status": "error", "message": "Invalid 'type'. Use '30days' or 'lifetime'."}), 400

    key = make_new_key()
    created = now_utc()

    if ktype == "30days":
        expires = created + timedelta(days=30)
        expires_str = iso(expires)
        validity = "30 Days"
        lifetime = False
    else:
        expires_str = None
        validity = "Lifetime"
        lifetime = True

    record = {
        "key": key,
        "type": ktype,
        "validity": validity,
        "created_at": iso(created),
        "expires_at": expires_str,
        "lifetime": "1" if lifetime else "0",
        "bound_fingerprint": "",
        "device_user_agent": "",
        "device_ip": "",
        "device_language": "",
        "bound_at": "",
    }
    storage_save(key, record)

    return jsonify({
        "status": "success",
        "message": f"{validity} key generate ho gayi aur save ho gayi.",
        "storage": MODE,
        "key": key,
        "type": ktype,
        "validity": validity,
        "created_at": iso(created),
        "expires_at": expires_str,
        "lifetime": lifetime
    })

@app.route("/check", methods=["GET", "POST"])
def check():
    body = request.get_json(silent=True) if request.method == "POST" else request.args
    key = (body.get("key") or "").strip().upper()
    if not key:
        return jsonify({"status": "error", "message": "Provide key via ?key=..."}), 400

    data = storage_get(key)

    if not data:
        return jsonify({"status": "success", "real": False, "valid": False, "key": key, "message": "❌ Key FAKE hai."})

    created = parse_iso(data.get("created_at") or "") or now_utc()
    now = now_utc()
    lifetime = is_true(data.get("lifetime"))

    # Device lock
    fp = device_fp()
    bound_fp = data.get("bound_fingerprint") or ""

    if not bound_fp:
        info = device_info()
        data["bound_fingerprint"] = fp
        data["device_user_agent"] = info["user_agent"]
        data["device_ip"] = info["ip"]
        data["device_language"] = info["language"]
        data["bound_at"] = iso(now)
        storage_save(key, data)
        device_status = "NEWLY_BOUND"
        device_message = "🔒 Key pehli baar isi device par lock ho gayi."
    elif bound_fp == fp:
        device_status = "SAME_DEVICE"
        device_message = "✅ Key isi device par already locked hai."
    else:
        return jsonify({
            "status": "success", "real": True, "valid": False, "device_mismatch": True, "key": key,
            "bound_device": {"ip": data.get("device_ip"), "ua": data.get("device_user_agent")},
            "current_device": device_info(),
            "message": "🚫 Ye key kisi dusre device par locked hai."
        })

    dev_out = {
        "ip": data.get("device_ip"),
        "user_agent": data.get("device_user_agent"),
        "bound_at": data.get("bound_at"),
        "status": device_status
    }

    if lifetime:
        return jsonify({
            "status": "success", "real": True, "valid": True, "expired": False, "key": key,
            "type": "lifetime", "remaining_readable": "Lifetime",
            "device": dev_out, "message": "✅ Lifetime key ACTIVE hai."
        })

    expires = parse_iso(data.get("expires_at") or "")
    remaining = int((expires - now).total_seconds()) if expires else 0

    if remaining <= 0:
        return jsonify({
            "status": "success", "real": True, "valid": False, "expired": True, "key": key,
            "remaining_readable": "0s", "device": dev_out, "message": "⏰ Key EXPIRE ho chuki hai."
        })

    return jsonify({
        "status": "success", "real": True, "valid": True, "expired": False, "key": key,
        "remaining_readable": format_remaining(remaining),
        "device": dev_out, "message": "✅ Key ACTIVE hai. Time chal raha hai."
    })

@app.route("/list")
def list_keys():
    allk = storage_all()
    now = now_utc()
    items = []
    for key, data in allk.items():
        lifetime = is_true(data.get("lifetime"))
        rem = None
        if not lifetime and data.get("expires_at"):
            exp = parse_iso(data["expires_at"])
            if exp: rem = max(0, int((exp - now).total_seconds()))
        items.append({
            "key": key, "type": data.get("type"), "expires_at": data.get("expires_at"),
            "remaining": "Lifetime" if lifetime else (format_remaining(rem) if rem is not None else None),
            "device_locked": bool(data.get("bound_fingerprint")),
            "device_ip": data.get("device_ip")
        })
    return jsonify({"status": "success", "storage": MODE, "total": len(items), "keys": items})

@app.route("/export")
def export_json():
    allk = storage_all()
    return Response(json.dumps(allk, indent=2), mimetype="application/json", headers={"Content-Disposition": 'attachment; filename="keys.json"'})

if __name__ == "__main__":
    if not os.path.exists(DATA_FILE):
        _save_json({})
    app.run(host="0.0.0.0", port=5000, debug=False)