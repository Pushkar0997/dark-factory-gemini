"""Tablekeeper stage 1 — reservations HTTP service (stdlib only + tzdata)."""
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit, parse_qsl, unquote
from zoneinfo import ZoneInfo

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
REF_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
LOCAL_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$")
DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
HHMM_RE = re.compile(r"^(\d{2}):(\d{2})$")
REF_RE = re.compile(r"^[A-Z0-9]{6,12}$")
DIGITS_RE = re.compile(r"^[0-9]+$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")
UTC = dt.timezone.utc

LOCK = threading.RLock()


class ApiError(Exception):
    def __init__(self, status, code, message=None):
        super().__init__(code)
        self.status, self.code, self.message = status, code, message or code


def bad(code="validation_failed", msg=None):
    return ApiError(422, code, msg)


def malformed(msg="malformed request"):
    return ApiError(400, "malformed_request", msg)


def not_found(msg="not found"):
    return ApiError(404, "not_found", msg)


# ---------------------------------------------------------------- passwords

def hash_password(pw):
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 13, r=8, p=1, dklen=32)
    return "scrypt$8192$8$1$%s$%s" % (base64.b64encode(salt).decode(), base64.b64encode(h).decode())


def check_password(pw, stored):
    try:
        _, n, r, p, salt, h = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r),
                             p=int(p), dklen=32)
        return hmac.compare_digest(got, base64.b64decode(h))
    except Exception:
        return False


# ---------------------------------------------------------------- time

def now_utc():
    return dt.datetime.now(UTC)


def iso(d):
    return d.isoformat(timespec="seconds")


def parse_hhmm(s):
    m = HHMM_RE.match(s) if isinstance(s, str) else None
    if not m:
        raise ValueError("bad HH:MM")
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 24 or mi > 59 or (h == 24 and mi):
        raise ValueError("bad HH:MM")
    return h * 60 + mi


def parse_date(s):
    m = DATE_RE.match(s) if isinstance(s, str) else None
    if not m:
        raise ValueError("bad date")
    return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def parse_local(s):
    """Return a naive datetime for a bare YYYY-MM-DDTHH:MM string or raise ValueError."""
    m = LOCAL_RE.match(s) if isinstance(s, str) else None
    if not m:
        raise ValueError("bad local")
    return dt.datetime(*(int(g) for g in m.groups()))


def resolve_local(naive, tz):
    """Resolve wall-clock to an aware UTC datetime (first occurrence); None if nonexistent."""
    aware = naive.replace(tzinfo=tz, fold=0)
    u = aware.astimezone(UTC)
    back = u.astimezone(tz).replace(tzinfo=None)
    if back != naive:
        return None
    return u


def local_minutes_to_naive(date, minutes):
    return dt.datetime(date.year, date.month, date.day) + dt.timedelta(minutes=minutes)


def fmt_local(naive):
    return naive.strftime("%Y-%m-%dT%H:%M")


# ---------------------------------------------------------------- state

def new_state():
    return {
        "users": {},          # id -> {id,email,display_name,pw_hash}
        "emails": {},         # lower email -> id
        "tokens": {},         # token -> user id
        "restaurants": {},    # id -> restaurant dict (fixture shape), ordered
        "reservations": {},   # id -> record
        "refs": {},           # reference -> id
        "idem": {},           # "user\x00method\x00path\x00key" -> receipt
        "seq": 0,
    }


STATE = new_state()


def next_id(state, prefix):
    state["seq"] += 1
    return "%s_%d" % (prefix, state["seq"])


def new_reference(state):
    while True:
        ref = "".join(secrets.choice(REF_ALPHABET) for _ in range(8))
        if ref not in state["refs"]:
            return ref


def tz_of(rest):
    return ZoneInfo(rest["timezone"])


def res_view(state, rec):
    rest = state["restaurants"][rec["restaurant_id"]]
    tz = tz_of(rest)
    start = dt.datetime.fromisoformat(rec["start_utc"])
    end = start + dt.timedelta(minutes=rest["reservation_duration_minutes"])
    out = {
        "reservation_id": rec["id"],
        "reference": rec["reference"],
        "restaurant_id": rec["restaurant_id"],
        "table_ids": list(rec["table_ids"]),
        "party_size": rec["party_size"],
        "status": rec["status"],
        "starts_at_local": rec["starts_at_local"],
        "starts_at": iso(start.astimezone(tz)),
        "ends_at": iso(end.astimezone(tz)),
        "created_at": rec["created_at"],
    }
    if len(rec["table_ids"]) == 1:
        out["table_id"] = rec["table_ids"][0]
    return out


def interval(state, rec):
    rest = state["restaurants"][rec["restaurant_id"]]
    s = dt.datetime.fromisoformat(rec["start_utc"])
    return s, s + dt.timedelta(minutes=rest["reservation_duration_minutes"])


def overlaps(a, b):
    return a[0] < b[1] and b[0] < a[1]


def hours_for(rest, date):
    wd = WEEKDAYS[date.weekday()]
    return [h for h in rest["opening_hours"] if h.get("weekday") == wd]


def check_slot(rest, naive):
    """Validate a local start time against opening hours, grid and DST; return start UTC."""
    try:
        return _check_slot(rest, naive)
    except (OverflowError, ValueError):
        raise bad("validation_failed", "local time is out of the supported range")


def _check_slot(rest, naive):
    tz = tz_of(rest)
    start = resolve_local(naive, tz)
    if start is None:
        raise bad("invalid_local_time", "local time does not exist")
    minute = naive.hour * 60 + naive.minute
    dur = dt.timedelta(minutes=rest["reservation_duration_minutes"])
    for h in hours_for(rest, naive.date()):
        o, c = parse_hhmm(h["opens"]), parse_hhmm(h["closes"])
        if o <= minute < c:
            if (minute - o) % rest["slot_minutes"] != 0:
                raise bad("not_on_slot_grid", "start is not on the slot grid")
            close_utc = local_minutes_to_naive(naive.date(), c).replace(tzinfo=tz, fold=0).astimezone(UTC)
            if start + dur > close_utc:
                raise bad("outside_opening_hours", "reservation would end after closing")
            (start + dur).astimezone(tz)  # ends_at must be representable
            return start
    raise bad("outside_opening_hours", "outside opening hours")


def check_party(v):
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        raise bad("validation_failed", "party_size must be a positive integer")
    return v


def table_of(rest, tid):
    for t in rest["tables"]:
        if t["id"] == tid:
            return t
    return None


def require_str(body, key, required=True):
    if key not in body or body[key] is None:
        if required:
            raise bad("validation_failed", "%s is required" % key)
        return None
    if not isinstance(body[key], str):
        raise malformed("%s must be a string" % key)
    return body[key]


def table_set(body, required=True):
    """Read table_id / table_ids from a body; returns a list of ids or None when absent."""
    has_one = body.get("table_id") is not None
    has_many = body.get("table_ids") is not None
    if has_one and has_many:
        raise bad("validation_failed", "send either table_id or table_ids, not both")
    if has_one:
        if not isinstance(body["table_id"], str):
            raise malformed("table_id must be a string")
        return [body["table_id"]]
    if has_many:
        ids = body["table_ids"]
        if not isinstance(ids, list) or not ids or not all(isinstance(t, str) for t in ids):
            raise bad("validation_failed", "table_ids must be a non-empty list of table ids")
        if len(set(ids)) != len(ids):
            raise bad("validation_failed", "duplicate table id")
        return list(ids)
    if required:
        raise bad("validation_failed", "table_id or table_ids is required")
    return None


def pair_order(rest, ids):
    """Return the pair in combinable order, or None if the pair is not declared."""
    for pair in rest.get("combinable") or []:
        if set(pair) == set(ids):
            return list(pair)
    return None


def validate_booking(state, rest_id, table_ids, starts_local, party):
    """Full POST /reservations validation; returns (rest, start_utc, ordered table ids)."""
    rest = state["restaurants"].get(rest_id)
    if rest is None:
        raise not_found("unknown restaurant")
    tables = [table_of(rest, t) for t in table_ids]
    if any(t is None for t in tables):
        raise not_found("unknown table")
    if len(table_ids) > 2:
        raise bad("combination_not_allowed", "at most two tables can be combined")
    if len(table_ids) == 2:
        ordered = pair_order(rest, table_ids)
        if ordered is None:
            raise bad("combination_not_allowed", "these tables cannot be combined")
        table_ids = ordered
    check_party(party)
    try:
        naive = parse_local(starts_local)
    except ValueError:
        raise bad("validation_failed", "starts_at_local must be YYYY-MM-DDTHH:MM")
    start = check_slot(rest, naive)
    if party > sum(t["capacity"] for t in tables):
        raise bad("party_exceeds_capacity", "party exceeds table capacity")
    return rest, start, list(table_ids)


def conflicts(state, rest, table_ids, start, exclude=()):
    end = start + dt.timedelta(minutes=rest["reservation_duration_minutes"])
    for rec in state["reservations"].values():
        if rec["status"] != "confirmed" or rec["id"] in exclude:
            continue
        if rec["restaurant_id"] != rest["id"] or not set(rec["table_ids"]) & set(table_ids):
            continue
        if overlaps((start, end), interval(state, rec)):
            return True
    return False


# ---------------------------------------------------------------- fixture

def check_id(v):
    if not isinstance(v, str) or not v or len(v) > 64:
        raise bad("validation_failed", "ids must be strings of 1..64 characters")
    return v


def build_from_fixture(fx):
    if not isinstance(fx, dict):
        raise malformed("fixture must be an object")
    st = new_state()
    try:
        users = fx.get("users") or []
        rests = fx.get("restaurants") or []
        reservations = fx.get("reservations") or []
        if not all(isinstance(x, list) for x in (users, rests, reservations)):
            raise bad()
        for u in users:
            uid = check_id(u["id"])
            email = u["email"]
            if uid in st["users"] or not isinstance(email, str) or email.lower() in st["emails"] \
                    or not isinstance(u["password"], str):
                raise bad("validation_failed", "duplicate or invalid user")
            st["users"][uid] = {"id": uid, "email": email,
                                "display_name": u.get("display_name", ""),
                                "pw_hash": hash_password(u["password"])}
            st["emails"][email.lower()] = uid
        for r in rests:
            rid = check_id(r["id"])
            if rid in st["restaurants"]:
                raise bad("validation_failed", "duplicate restaurant id")
            ZoneInfo(r["timezone"])
            tables = []
            for t in r.get("tables") or []:
                if any(x["id"] == t["id"] for x in tables) or isinstance(t["capacity"], bool) \
                        or not isinstance(t["capacity"], int):
                    raise bad("validation_failed", "duplicate table or bad capacity")
                tables.append({**t, "id": check_id(t["id"])})
            hours = []
            for h in r.get("opening_hours") or []:
                if h["weekday"] not in WEEKDAYS or parse_hhmm(h["opens"]) >= parse_hhmm(h["closes"]):
                    raise bad("validation_failed", "bad opening hours")
                hours.append(dict(h))
            combinable = []
            for pair in r.get("combinable") or []:
                if not isinstance(pair, list) or len(pair) != 2 or pair[0] == pair[1] \
                        or not all(any(t["id"] == x for t in tables) for x in pair):
                    raise bad("validation_failed", "combinable entries are pairs of the restaurant's tables")
                combinable.append(list(pair))
            rest = {**r, "tables": tables, "opening_hours": hours, "combinable": combinable}
            for k in ("slot_minutes", "reservation_duration_minutes", "cancellation_cutoff_minutes"):
                if isinstance(rest[k], bool) or not isinstance(rest[k], int):
                    raise bad()
            if rest["slot_minutes"] < 1 or rest["reservation_duration_minutes"] < 1:
                raise bad()
            st["restaurants"][rid] = rest
        for b in reservations:
            rid = check_id(b["id"])
            rest = st["restaurants"][b["restaurant_id"]]
            naive = parse_local(b["starts_at_local"])
            start = naive.replace(tzinfo=tz_of(rest), fold=0).astimezone(UTC)
            (start + dt.timedelta(minutes=rest["reservation_duration_minutes"])).astimezone(tz_of(rest))
            ref = b.get("reference")
            if ref is None:
                ref = new_reference(st)
            if not isinstance(ref, str) or not REF_RE.match(ref) or ref in st["refs"]:
                raise bad("validation_failed", "reference must be 6..12 of A-Z0-9 and unique")
            if rid in st["reservations"] or check_id(b["user_id"]) not in st["users"]:
                raise bad("validation_failed", "duplicate id or unknown user")
            tids = [b["table_id"]] if b.get("table_id") is not None else b["table_ids"]
            if not isinstance(tids, list) or not tids or len(tids) > 2 or len(set(tids)) != len(tids) \
                    or any(table_of(rest, t) is None for t in tids):
                raise bad("validation_failed", "unknown table")
            if len(tids) == 2:
                tids = pair_order(rest, tids) or list(tids)
            if b.get("status", "confirmed") not in ("confirmed", "cancelled"):
                raise bad("validation_failed", "bad status")
            st["reservations"][rid] = {
                "id": rid, "reference": ref, "user_id": b.get("user_id"),
                "restaurant_id": rest["id"], "table_ids": tids,
                "party_size": b.get("party_size"), "status": b.get("status", "confirmed"),
                "starts_at_local": fmt_local(naive), "start_utc": iso(start),
                "created_at": b.get("created_at") or iso(now_utc().replace(microsecond=0)),
            }
            st["refs"][ref] = rid
    except ApiError:
        raise
    except Exception as e:
        raise bad("validation_failed", "invalid fixture: %s" % e)
    return st


def validate_state(st):
    """Check an imported state object; raise on anything unusable."""
    keys = ("users", "emails", "tokens", "restaurants", "reservations", "refs", "idem", "seq")
    if not isinstance(st, dict) or any(k not in st for k in keys):
        raise ValueError("missing keys")
    for k in keys[:-1]:
        if not isinstance(st[k], dict):
            raise ValueError("bad %s" % k)
    if isinstance(st["seq"], bool) or not isinstance(st["seq"], int):
        raise ValueError("bad seq")
    for u in st["users"].values():
        for f in ("id", "email", "display_name", "pw_hash"):
            if not isinstance(u.get(f), str):
                raise ValueError("bad user")
    for r in st["restaurants"].values():
        r.setdefault("combinable", [])
        if not isinstance(r["combinable"], list):
            raise ValueError("bad combinable")
        ZoneInfo(r["timezone"])
        for f in ("slot_minutes", "reservation_duration_minutes", "cancellation_cutoff_minutes"):
            if not isinstance(r[f], int):
                raise ValueError("bad restaurant")
        if not isinstance(r["tables"], list) or not isinstance(r["opening_hours"], list):
            raise ValueError("bad restaurant")
    for rec in st["reservations"].values():
        if rec["restaurant_id"] not in st["restaurants"]:
            raise ValueError("bad reservation")
        dt.datetime.fromisoformat(rec["start_utc"])
        if "table_ids" not in rec:  # stage-1 export
            rec["table_ids"] = [rec.pop("table_id")]
        rec.pop("table_id", None)
        if not isinstance(rec["table_ids"], list) or not all(isinstance(t, str) for t in rec["table_ids"]):
            raise ValueError("bad reservation")
        for f in ("id", "reference", "status", "starts_at_local", "created_at"):
            if not isinstance(rec.get(f), str):
                raise ValueError("bad reservation")
    for v in st["tokens"].values():
        if v not in st["users"]:
            raise ValueError("bad token")
    for rc in st["idem"].values():
        if not isinstance(rc, dict) or "body" not in rc or "response" not in rc:
            raise ValueError("bad receipt")
    return st


# ---------------------------------------------------------------- handlers

def canon(body):
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def authenticate(headers):
    h = headers.get("Authorization") or ""
    parts = h.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise ApiError(401, "unauthenticated", "missing or malformed bearer token")
    with LOCK:
        uid = STATE["tokens"].get(parts[1].strip())
        if uid is None or uid not in STATE["users"]:
            raise ApiError(401, "unauthenticated", "unknown token")
        return uid


def parse_object(raw):
    try:
        body = json.loads(raw.decode("utf-8"))
    except Exception:
        raise malformed("body is not valid JSON")
    if not isinstance(body, dict):
        raise malformed("body must be a JSON object")
    return body


def idem_key(headers):
    key = headers.get("Idempotency-Key")
    if key is None or key == "":
        raise ApiError(400, "missing_idempotency_key", "Idempotency-Key header is required")
    if len(key) > 255:
        raise bad("validation_failed", "Idempotency-Key must be 1..255 characters")
    return key


def with_idempotency(uid, method, path, key, body, fn):
    """Run fn() under the global lock with replay semantics. fn returns (status, obj)."""
    slot = "\x00".join((uid, method, path, key))
    c = canon(body)
    with LOCK:
        rc = STATE["idem"].get(slot)
        if rc is not None:
            if rc["body"] != c:
                raise ApiError(409, "idempotency_key_reuse", "key reused with a different body")
            return 200, rc["response"]
        status, obj = fn()
        STATE["idem"][slot] = {"body": c, "status": status, "response": obj}
        return status, obj


def h_signup(body):
    email = require_str(body, "email")
    pw = require_str(body, "password")
    name = require_str(body, "display_name", required=False)
    if not EMAIL_RE.match(email):
        raise bad("validation_failed", "email must be local@domain")
    if len(pw) < 8:
        raise bad("validation_failed", "password must be at least 8 characters")
    if name is None:
        name = email.split("@")[0]
    with LOCK:
        if email.lower() in STATE["emails"]:
            raise ApiError(409, "email_taken", "email already registered")
    pw_hash = hash_password(pw)
    with LOCK:
        if email.lower() in STATE["emails"]:
            raise ApiError(409, "email_taken", "email already registered")
        uid = next_id(STATE, "u")
        while uid in STATE["users"]:
            uid = next_id(STATE, "u")
        STATE["users"][uid] = {"id": uid, "email": email, "display_name": name, "pw_hash": pw_hash}
        STATE["emails"][email.lower()] = uid
        token = secrets.token_urlsafe(32)
        STATE["tokens"][token] = uid
    return 201, {"user_id": uid, "display_name": name, "token": token}


def h_login(body):
    email = require_str(body, "email")
    pw = require_str(body, "password")
    with LOCK:
        uid = STATE["emails"].get(email.lower())
        user = STATE["users"].get(uid) if uid else None
        stored = user["pw_hash"] if user else None
        st = STATE
    if user is None or not check_password(pw, stored):
        raise ApiError(401, "unauthenticated", "wrong email or password")
    with LOCK:
        if STATE is not st:
            raise ApiError(401, "unauthenticated", "wrong email or password")
        token = secrets.token_urlsafe(32)
        STATE["tokens"][token] = uid
    return 200, {"user_id": uid, "display_name": user["display_name"], "token": token}


def h_restaurants():
    with LOCK:
        return 200, {"restaurants": [{"id": r["id"], "name": r.get("name"), "timezone": r["timezone"]}
                                     for r in STATE["restaurants"].values()]}


def h_restaurant(rid):
    with LOCK:
        r = STATE["restaurants"].get(rid)
        if r is None:
            raise not_found("unknown restaurant")
        return 200, json.loads(json.dumps(r))


def h_availability(q):
    for k in ("restaurant_id", "date", "party_size"):
        if k not in q:
            raise bad("validation_failed", "%s is required" % k)
    if not DIGITS_RE.match(q["party_size"]):
        raise bad("validation_failed", "party_size must be plain digits")
    party = int(q["party_size"])
    if party < 1:
        raise bad("validation_failed", "party_size must be at least 1")
    try:
        date = parse_date(q["date"])
    except ValueError:
        raise bad("validation_failed", "date must be YYYY-MM-DD")
    with LOCK:
        rest = STATE["restaurants"].get(q["restaurant_id"])
        if rest is None:
            raise not_found("unknown restaurant")
        try:
            return _availability(rest, date, party)
        except (OverflowError, ValueError):
            raise bad("validation_failed", "date is out of the supported range")


def _availability(rest, date, party):
    tz = tz_of(rest)
    dur = dt.timedelta(minutes=rest["reservation_duration_minutes"])
    busy = {}
    cap = {t["id"]: t["capacity"] for t in rest["tables"]}
    for rec in STATE["reservations"].values():
        if rec["status"] == "confirmed" and rec["restaurant_id"] == rest["id"]:
            for tid in rec["table_ids"]:
                busy.setdefault(tid, []).append(interval(STATE, rec))
    slots, seen = [], set()
    for h in hours_for(rest, date):
        o, c = parse_hhmm(h["opens"]), parse_hhmm(h["closes"])
        close_utc = local_minutes_to_naive(date, c).replace(tzinfo=tz, fold=0).astimezone(UTC)
        m = o
        while m < c:
            naive = local_minutes_to_naive(date, m)
            m += rest["slot_minutes"]
            if naive.date() != date:
                break
            start = resolve_local(naive, tz)
            if start is None or start + dur > close_utc or naive in seen:
                continue
            seen.add(naive)
            iv = (start, start + dur)
            free = {t["id"] for t in rest["tables"]
                    if not any(overlaps(iv, b) for b in busy.get(t["id"], ()))}
            avail = [t["id"] for t in rest["tables"] if t["capacity"] >= party and t["id"] in free]
            options = [{"table_ids": [tid], "capacity": cap[tid]} for tid in avail]
            for pair in rest.get("combinable") or []:
                total = cap[pair[0]] + cap[pair[1]]
                if total >= party and pair[0] in free and pair[1] in free:
                    options.append({"table_ids": list(pair), "capacity": total})
            slots.append({"starts_at_local": fmt_local(naive),
                          "starts_at": iso(start.astimezone(tz)),
                          "available_table_ids": avail,
                          "available_options": options})
    slots.sort(key=lambda s: s["starts_at_local"])
    return 200, {"restaurant_id": rest["id"], "date": date.isoformat(),
                 "timezone": rest["timezone"], "slots": slots}


def h_create(uid, body):
    rest_id = require_str(body, "restaurant_id")
    table_ids = table_set(body)
    if "starts_at_local" not in body or body["starts_at_local"] is None:
        raise bad("validation_failed", "starts_at_local is required")
    if not isinstance(body["starts_at_local"], str):
        raise bad("validation_failed", "starts_at_local must be YYYY-MM-DDTHH:MM")
    if "party_size" not in body:
        raise bad("validation_failed", "party_size is required")
    party = body["party_size"]
    rest, start, table_ids = validate_booking(STATE, rest_id, table_ids, body["starts_at_local"], party)
    if conflicts(STATE, rest, table_ids, start):
        raise ApiError(409, "table_unavailable", "table is taken for that time")
    rid = next_id(STATE, "res")
    while rid in STATE["reservations"]:
        rid = next_id(STATE, "res")
    ref = new_reference(STATE)
    rec = {"id": rid, "reference": ref, "user_id": uid, "restaurant_id": rest["id"],
           "table_ids": table_ids, "party_size": party, "status": "confirmed",
           "starts_at_local": body["starts_at_local"], "start_utc": iso(start),
           "created_at": iso(now_utc().replace(microsecond=0))}
    STATE["reservations"][rid] = rec
    STATE["refs"][ref] = rid
    return 201, res_view(STATE, rec)


def own_reservation(uid, ref):
    rid = STATE["refs"].get(ref)
    rec = STATE["reservations"].get(rid) if rid else None
    if rec is None or rec["user_id"] != uid:
        raise not_found("no such reservation")
    return rec


def check_cutoff(rec):
    rest = STATE["restaurants"][rec["restaurant_id"]]
    start = dt.datetime.fromisoformat(rec["start_utc"])
    if now_utc() >= start - dt.timedelta(minutes=rest["cancellation_cutoff_minutes"]):
        raise ApiError(409, "cutoff_passed", "too close to the reservation start")


def h_list(uid):
    with LOCK:
        mine = [r for r in STATE["reservations"].values() if r["user_id"] == uid]
        mine.sort(key=lambda r: (dt.datetime.fromisoformat(r["start_utc"]), r["created_at"]), reverse=True)
        return 200, {"reservations": [res_view(STATE, r) for r in mine]}


def h_get(uid, ref):
    with LOCK:
        return 200, res_view(STATE, own_reservation(uid, ref))


def h_cancel(uid, ref):
    with LOCK:
        rec = own_reservation(uid, ref)
        if rec["status"] == "cancelled":
            return 200, res_view(STATE, rec)
        check_cutoff(rec)
        rec["status"] = "cancelled"
        return 200, res_view(STATE, rec)


def item_fields(item):
    """Type-check optional amendment fields; returns dict of supplied fields."""
    out = {}
    tids = table_set(item, required=False)
    if tids is not None:
        out["table_ids"] = tids
    if item.get("starts_at_local") is not None:
        if not isinstance(item["starts_at_local"], str):
            raise bad("validation_failed", "starts_at_local must be YYYY-MM-DDTHH:MM")
        out["starts_at_local"] = item["starts_at_local"]
    if "party_size" in item:
        out["party_size"] = item["party_size"]
    return out


def plan_change(rec, fields):
    """Validate an amendment of rec; return the new (table, local, party, start_utc) or None if no-op."""
    table = fields.get("table_ids", rec["table_ids"])
    local = fields.get("starts_at_local", rec["starts_at_local"])
    party = fields.get("party_size", rec["party_size"])
    if "party_size" in fields:
        check_party(party)
    if (sorted(table), local, party) == (sorted(rec["table_ids"]), rec["starts_at_local"], rec["party_size"]) \
            and not isinstance(party, bool):
        return None
    _, start, table = validate_booking(STATE, rec["restaurant_id"], table, local, party)
    return table, local, party, iso(start)


def h_patch(uid, ref, body):
    fields = item_fields(body)
    with LOCK:
        rec = own_reservation(uid, ref)
        if rec["status"] == "cancelled":
            raise ApiError(409, "reservation_cancelled", "reservation is cancelled")
        check_cutoff(rec)
        change = plan_change(rec, fields)
        if change is None:
            return 200, res_view(STATE, rec)
        table, local, party, start = change
        rest = STATE["restaurants"][rec["restaurant_id"]]
        if conflicts(STATE, rest, table, dt.datetime.fromisoformat(start), exclude=(rec["id"],)):
            raise ApiError(409, "table_unavailable", "table is taken for that time")
        rec.update(table_ids=table, starts_at_local=local, party_size=party, start_utc=start)
        return 200, res_view(STATE, rec)


def check_moves_shape(body):
    moves = body.get("moves")
    if not isinstance(moves, list) or not 1 <= len(moves) <= 8:
        raise bad("validation_failed", "moves must be a list of 1..8 objects")
    refs = set()
    for m in moves:
        if not isinstance(m, dict) or not isinstance(m.get("reference"), str):
            raise bad("validation_failed", "each move needs a string reference")
        if m["reference"] in refs:
            raise bad("validation_failed", "duplicate reference")
        refs.add(m["reference"])
    return moves


def h_moves(uid, body):
    moves = check_moves_shape(body)
    recs, plans, rest_id = [], [], None
    for m in moves:
        fields = item_fields(m)
        rec = own_reservation(uid, m["reference"])
        if rest_id is None:
            rest_id = rec["restaurant_id"]
        elif rec["restaurant_id"] != rest_id:
            raise bad("validation_failed", "all bookings must belong to the same restaurant")
        if rec["status"] == "cancelled":
            raise ApiError(409, "reservation_cancelled", "reservation is cancelled")
        check_cutoff(rec)
        change = plan_change(rec, fields)
        if change is None:
            change = (rec["table_ids"], rec["starts_at_local"], rec["party_size"], rec["start_utc"])
        recs.append(rec)
        plans.append(change)
    rest = STATE["restaurants"][rest_id]
    dur = dt.timedelta(minutes=rest["reservation_duration_minutes"])
    listed = {r["id"] for r in recs}
    results = []
    for (table, _, _, start) in plans:
        s = dt.datetime.fromisoformat(start)
        results.append((table, (s, s + dur)))
    for i in range(len(results)):
        for j in range(i + 1, len(results)):
            if set(results[i][0]) & set(results[j][0]) and overlaps(results[i][1], results[j][1]):
                raise ApiError(409, "table_unavailable", "moved bookings overlap")
        if conflicts(STATE, rest, results[i][0], results[i][1][0], exclude=listed):
            raise ApiError(409, "table_unavailable", "table is taken for that time")
    for rec, (table, local, party, start) in zip(recs, plans):
        rec.update(table_ids=table, starts_at_local=local, party_size=party, start_utc=start)
    return 201, {"reservations": [res_view(STATE, r) for r in recs]}


def h_reset(body):
    global STATE
    st = build_from_fixture(body)
    with LOCK:
        STATE = st
    return 204, None


def h_export():
    with LOCK:
        snap = json.loads(json.dumps(STATE))
    return 200, {"track": "tablekeeper", "format_version": 1, "state": snap}


def h_import(body):
    global STATE
    if body.get("track") != "tablekeeper":
        raise bad("validation_failed", "wrong track")
    v = body.get("format_version")
    if isinstance(v, bool) or v != 1:
        raise bad("validation_failed", "wrong format_version")
    try:
        st = validate_state(json.loads(json.dumps(body.get("state"))))
    except Exception:
        raise bad("validation_failed", "invalid state")
    with LOCK:
        STATE = st
    return 204, None


# ---------------------------------------------------------------- HTTP

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
SCREENS = ("/", "/signup", "/login", "/lookup")
STATIC_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                ".js": "application/javascript; charset=utf-8", ".svg": "image/svg+xml"}


def static_file(name):
    """Return (bytes, content type) for a file in STATIC_DIR, or None."""
    if "/" in name or name.startswith(".") or os.path.splitext(name)[1] not in STATIC_TYPES:
        return None
    path = os.path.join(STATIC_DIR, name)
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return f.read(), STATIC_TYPES[os.path.splitext(name)[1]]


class Page:
    def __init__(self, data, ctype):
        self.data, self.ctype = data, ctype


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "tablekeeper"

    def log_message(self, *a):
        pass

    def send(self, status, obj=None):
        head = getattr(self, "command", None) == "HEAD"
        if isinstance(obj, Page):
            body, ctype = obj.data, obj.ctype
        else:
            body = b"" if obj is None else json.dumps(obj, ensure_ascii=False).encode("utf-8")
            ctype = "application/json; charset=utf-8"
        self.send_response(status)
        if obj is not None:
            self.send_header("Content-Type", ctype)
            if isinstance(obj, Page):
                self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body and not head:
            self.wfile.write(body)

    def read_body(self):
        n = self.headers.get("Content-Length")
        try:
            n = int(n) if n else 0
        except ValueError:
            n = 0
        return self.rfile.read(n) if n > 0 else b""

    def handle_any(self, method):
        try:
            raw = self.read_body() if method in ("POST", "PATCH", "PUT") else b""
            parts = urlsplit(self.path)
            path = parts.path.rstrip("/") or "/"
            q = {}
            for k, v in parse_qsl(parts.query, keep_blank_values=True):
                q.setdefault(k, v)
            status, obj = self.route(method, path, q, raw)
            self.send(status, obj)
        except ApiError as e:
            self.send(e.status, {"error": {"code": e.code, "message": e.message}})
        except Exception as e:  # never leak a bare 5xx without the error body
            try:
                self.send(500, {"error": {"code": "internal_error", "message": str(e)}})
            except Exception:
                pass

    def route(self, method, path, q, raw):
        seg = [unquote(s) for s in path.split("/")[1:]]
        if method == "HEAD":
            method = "GET"
        h = self.headers
        if method == "GET":
            if path == "/health":
                return 200, {"status": "ok"}
            if path in SCREENS:
                return 200, Page(*static_file("index.html"))
            if len(seg) == 2 and seg[0] == "static":
                found = static_file(seg[1])
                if found is None:
                    raise not_found("no such file")
                return 200, Page(*found)
            if path == "/restaurants":
                return h_restaurants()
            if len(seg) == 2 and seg[0] == "restaurants":
                return h_restaurant(seg[1])
            if path == "/availability":
                return h_availability(q)
            if path == "/_test/export":
                return h_export()
            if path == "/reservations":
                return h_list(authenticate(h))
            if len(seg) == 2 and seg[0] == "reservations":
                return h_get(authenticate(h), seg[1])
        elif method == "POST":
            if path == "/_test/reset":
                return h_reset(parse_object(raw))
            if path == "/_test/import":
                return h_import(parse_object(raw))
            if path == "/auth/signup":
                return h_signup(parse_object(raw))
            if path == "/auth/login":
                return h_login(parse_object(raw))
            if path in ("/reservations", "/reservation-moves"):
                uid = authenticate(h)
                body = parse_object(raw)
                key = idem_key(h)
                fn = (lambda: h_create(uid, body)) if path == "/reservations" else (lambda: h_moves(uid, body))
                return with_idempotency(uid, method, path, key, body, fn)
            if len(seg) == 3 and seg[0] == "reservations" and seg[2] == "cancel":
                return h_cancel(authenticate(h), seg[1])
        elif method == "PATCH":
            if len(seg) == 2 and seg[0] == "reservations":
                uid = authenticate(h)
                return h_patch(uid, seg[1], parse_object(raw))
        raise not_found("no such route")

    def do_GET(self):
        self.handle_any("GET")

    def do_POST(self):
        self.handle_any("POST")

    def do_PATCH(self):
        self.handle_any("PATCH")

    def do_HEAD(self):
        self.handle_any("HEAD")

    def do_OPTIONS(self):
        self.handle_any("OPTIONS")

    def send_error(self, code, message=None, explain=None):
        status = 404 if code in (501, 405) else (code if 400 <= code < 500 else 400)
        err_code = "not_found" if status == 404 else "malformed_request"
        try:
            self.close_connection = True
            self.send(status, {"error": {"code": err_code, "message": message or "bad request"}})
        except Exception:
            pass

    def do_PUT(self):
        self.handle_any("PUT")

    def do_DELETE(self):
        self.handle_any("DELETE")


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 256


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    Server(("0.0.0.0", port), Handler).serve_forever()
