# app.py — Hybrid keys.json (local) + Upstash Redis (Vercel)
import os
import json
import hashlib
import time
import secrets
import string
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

KEY_PREFIX = "KHAN"
DAY_SECONDS = 86400
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "keys.json")

# ---------- backend auto-detect ----------
REDIS_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
USE_REDIS = bool(REDIS_URL and REDIS_TOKEN)

redis = None
if USE_REDIS:
    try:
        from upstash_redis import Redis
        redis = Redis(url=REDIS_URL, token=REDIS_TOKEN)
    except Exception:
        USE_REDIS = False

ON_VERCEL = bool(os.environ.get("VERCEL"))
MODE = "redis" if USE_REDIS else "json"
if ON_VERCEL and not USE_REDIS:
    print("⚠️  WARNING: Vercel par keys.json read-only hai. "
          "UPSTASH_REDIS_REST_URL & TOKEN set karo, warna data persist nahi hoga.")


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
        d = redis.hgetall(f"key:{key}")
        return d if d else None
    return _load_json().get(key)

def storage_save(key, data):
    if USE_REDIS:
        clean = {k: ("" if v is None else str(v)) for k, v in data.items()}
        redis.hset(f"key:{key}", values=clean)
    else:
        allk = _load_json()
        allk[key] = data
        _save_json(allk)

def storage_all():
    if USE_REDIS:
        out = {}
        for k in redis.keys("key:*"):
            d = redis.hgetall(k)
            if d:
                out[d.get("key") or k.replace("key:", "")] = d
        return out
    return _load_json()

def storage_delete(key):
    if USE_REDIS:
        redis.delete(f"key:{key}")
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
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("1", "true", "yes")

def format_remaining(sec):
    if sec <= 0:
        return "0s"
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
    if not raw:
        return None
    v = raw.strip().lower()
    if v in ("30", "30days", "30d", "30day", "month", "monthly", "one_month"):
        return "30days"
    if v in ("life", "lifetime", "life_time", "forever", "unlimited", "infinite", "inf"):
        return "lifetime"
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
        "version": "3.0 (hybrid storage + device lock)",
        "storage_mode": MODE,
        "storage_location": "Upstash Redis" if USE_REDIS else DATA_FILE,
        "endpoints": {
            "generate_30days": "/generate?type=30days",
            "generate_lifetime": "/generate?type=lifetime",
            "check": "/check?key=KHAN-XXXX-XXXX-XXXX",
            "list": "/list",
            "export_json": "/export    → saari keys keys.json ke roop me download",
            "delete": "/delete?key=...&secret=ADMIN_SECRET"
        },
        "rules": "Ek key = ek device. Pehli /check par current device lock ho jata hai."
    })


@app.route("/generate", methods=["GET", "POST"])
def generate():
    body = request.get_json(silent=True) if request.method == "POST" else request.args
    raw = (body.get("type") or body.get("plan") or "")
    ktype = normalize_type(raw)

    if not ktype:
        return jsonify({
            "status": "error",
            "message": "Invalid 'type'. Use '30days' or 'lifetime'.",
            "example": "/generate?type=30days"
        }), 400

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
        "lifetime": lifetime,
        "bound_fingerprint": None,
        "device_user_agent": None,
        "device_ip": None,
        "device_language": None,
        "bound_at": None,
    }
    storage_save(key, record)

    return jsonify({
        "status": "success",
        "message": f"{validity} key generate ho gayi aur {MODE} storage me save ho gayi.",
        "storage": MODE,
        "key": key,
        "type": ktype,
        "validity": validity,
        "created_at": iso(created),
        "expires_at": expires_str,
        "lifetime": lifetime,
        "device_lock": "Pehli /check par current device lock ho jayega."
    })


@app.route("/check", methods=["GET", "POST"])
def check():
    body = request.get_json(silent=True) if request.method == "POST" else request.args
    key = (body.get("key") or "").strip().upper()
    if not key:
        return jsonify({
            "status": "error",
            "message": "Provide key via ?key=... or JSON {'key': 'KHAN-...'}"
        }), 400

    data = storage_get(key)

    if not data:
        return jsonify({
            "status": "success",
            "real": False,
            "valid": False,
            "expired": None,
            "key": key,
            "storage": MODE,
            "message": "❌ Ye key FAKE hai / database me nahi mili."
        })

    created = parse_iso(data.get("created_at") or "") or now_utc()
    now = now_utc()
    lifetime = is_true(data.get("lifetime"))

    # ----- device lock -----
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
        bound_fp = fp
        device_status = "NEWLY_BOUND"
        device_message = "🔒 Key pehli baar isi device par lock ho gayi."
    elif bound_fp == fp:
        device_status = "SAME_DEVICE"
        device_message = "✅ Key isi device par already locked hai."
    else:
        return jsonify({
            "status": "success",
            "real": True,
            "valid": False,
            "expired": None,
            "device_mismatch": True,
            "key": key,
            "bound_device": {
                "user_agent": data.get("device_user_agent"),
                "ip": data.get("device_ip"),
                "language": data.get("device_language"),
                "bound_at": data.get("bound_at"),
            },
            "current_device": device_info(),
            "message": "🚫 Ye key kisi dusre device par locked hai. Is device par nahi chalegi."
        })

    dev_out = {
        "user_agent": data.get("device_user_agent"),
        "ip": data.get("device_ip"),
        "language": data.get("device_language"),
        "bound_at": data.get("bound_at"),
        "fingerprint": bound_fp[:12] + "...",
        "status": device_status,
    }

    # ----- lifetime -----
    if lifetime:
        age = int((now - created).total_seconds())
        return jsonify({
            "status": "success",
            "real": True,
            "valid": True,
            "expired": False,
            "device_mismatch": False,
            "storage": MODE,
            "key": key,
            "type": "lifetime",
            "validity": "Lifetime",
            "created_at": data.get("created_at"),
            "expires_at": None,
            "remaining_seconds": None,
            "remaining_readable": "Lifetime — never expires",
            "age_seconds": age,
            "age_readable": format_remaining(age),
            "device": dev_out,
            "device_message": device_message,
            "message": "✅ Key REAL aur ACTIVE hai. Lifetime — is device par hamesha chalegi."
        })

    # ----- 30 days -----
    expires = parse_iso(data.get("expires_at") or "")
    if not expires:
        return jsonify({
            "status": "success",
            "real": True,
            "valid": False,
            "expired": True,
            "key": key,
            "message": "Key record corrupted (missing expiry)."
        })

    remaining = int((expires - now).total_seconds())

    if remaining <= 0:
        return jsonify({
            "status": "success",
            "real": True,
            "valid": False,
            "expired": True,
            "device_mismatch": False,
            "storage": MODE,
            "key": key,
            "type": data.get("type"),
            "validity": data.get("validity"),
            "created_at": data.get("created_at"),
            "expires_at": data.get("expires_at"),
            "remaining_seconds": 0,
            "remaining_readable": "0s (expired)",
            "device": dev_out,
            "message": "⏰ Key REAL hai lekin EXPIRE ho chuki hai."
        })

    d, rem = divmod(remaining, DAY_SECONDS)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)

    return jsonify({
        "status": "success",
        "real": True,
        "valid": True,
        "expired": False,
        "device_mismatch": False,
        "storage": MODE,
        "key": key,
        "type": data.get("type"),
        "validity": data.get("validity"),
        "created_at": data.get("created_at"),
        "expires_at": data.get("expires_at"),
        "remaining_seconds": remaining,
        "remaining_days": d,
        "remaining_hours": h,
        "remaining_minutes": m,
        "remaining_seconds_only": s,
        "remaining_readable": format_remaining(remaining),
        "device": dev_out,
        "device_message": device_message,
        "message": "✅ Key REAL aur ACTIVE hai. Time chal raha hai. Locked to this device."
    })


@app.route("/list")
def list_keys():
    allk = storage_all()
    now = now_utc()
    items = []

    for key, data in allk.items():
        remaining = None
        lifetime = is_true(data.get("lifetime"))
        if not lifetime and data.get("expires_at"):
            exp = parse_iso(data["expires_at"])
            if exp:
                remaining = max(0, int((exp - now).total_seconds()))

        items.append({
            "key": key,
            "type": data.get("type"),
            "validity": data.get("validity"),
            "created_at": data.get("created_at"),
            "expires_at": data.get("expires_at") or None,
            "remaining_seconds": remaining,
            "remaining_readable": "Lifetime" if lifetime else (
                format_remaining(remaining) if remaining is not None else None
            ),
            "device": {
                "locked": bool(data.get("bound_fingerprint")),
                "user_agent": data.get("device_user_agent") or None,
                "ip": data.get("device_ip") or None,
                "language": data.get("device_language") or None,
                "bound_at": data.get("bound_at") or None,
            }
        })

    return jsonify({
        "status": "success",
        "storage": MODE,
        "total": len(items),
        "keys": items
    })


@app.route("/export")
def export_json():
    """
    Poore database ko keys.json ke roop me download karo.
    Local mode: keys.json se padhta hai.
    Redis mode: Redis se padh kar keys.json file bana deta hai.
    """
    allk = storage_all()

    # local JSON ke liye native types
    out = {}
    for k, d in allk.items():
        out[k] = {
            "key": d.get("key") or k,
            "type": d.get("type"),
            "validity": d.get("validity"),
            "created_at": d.get("created_at"),
            "expires_at": d.get("expires_at") or None,
            "lifetime": is_true(d.get("lifetime")),
            "bound_fingerprint": d.get("bound_fingerprint") or None,
            "device_user_agent": d.get("device_user_agent") or None,
            "device_ip": d.get("device_ip") or None,
            "device_language": d.get("device_language") or None,
            "bound_at": d.get("bound_at") or None,
        }

    payload = json.dumps(out, indent=2, ensure_ascii=False)
    return Response(
        payload,
        mimetype="application/json",
        headers={"Content-Disposition": 'attachment; filename="keys.json"'}
    )


@app.route("/delete", methods=["GET", "POST"])
def delete_key():
    secret = os.environ.get("ADMIN_SECRET")
    if not secret:
        return jsonify({
            "status": "error",
            "message": "Delete disabled. Set ADMIN_SECRET env var."
        }), 403

    body = request.get_json(silent=True) if request.method == "POST" else request.args
    if body.get("secret") != secret:
        return jsonify({"status": "error", "message": "Invalid secret."}), 403

    key = (body.get("key") or "").strip().upper()
    if not key:
        return jsonify({"status": "error", "message": "Missing key."}), 400

    if not storage_get(key):
        return jsonify({"status": "error", "message": "Key not found."}), 404

    storage_delete(key)
    return jsonify({"status": "success", "message": f"Key {key} delete ho gayi.", "storage": MODE})


# ---------- bootstrap ----------
if __name__ == "__main__":
    if not USE_REDIS and not os.path.exists(DATA_FILE):
        _save_json({})
        print(f"📁 Created {DATA_FILE}")
    print(f"▶️  Storage mode: {MODE}")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)