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
        "meta": {},           # restaurant id -> {"policies": [...], "revision": int}
        "reservations": {},   # id -> record
        "refs": {},           # reference -> id
        "series": {},         # id -> series record
        "plans": {},          # plan id -> seating plan (preview, possibly applied)
        "idem": {},           # "user\x00method\x00path\x00key" -> receipt
        "seq": 0,
    }


STATE = new_state()
TERM_FIELDS = ("slot_minutes", "reservation_duration_minutes", "cancellation_cutoff_minutes",
               "opening_hours", "capacities")


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


def now_iso():
    return iso(now_utc().replace(microsecond=0))


def copy(v):
    return json.loads(json.dumps(v))


# ---------------------------------------------------------------- policies

def policy_zero(rest):
    return {"policy_version": 0,
            "slot_minutes": rest["slot_minutes"],
            "reservation_duration_minutes": rest["reservation_duration_minutes"],
            "cancellation_cutoff_minutes": rest["cancellation_cutoff_minutes"],
            "opening_hours": copy(rest["opening_hours"]),
            "capacities": {t["id"]: t["capacity"] for t in rest["tables"]}}


def select_policy(state, rest, date):
    """The policy in force for a local calendar date: greatest effective_from <= date, then version."""
    best, best_key = policy_zero(rest), None
    for p in state["meta"][rest["id"]]["policies"]:
        ef = parse_date(p["effective_from"])
        key = (ef, p["policy_version"])
        if ef <= date and (best_key is None or key > best_key):
            best, best_key = p, key
    return best


def terms_of(policy):
    out = {"policy_version": policy["policy_version"]}
    for k in TERM_FIELDS:
        out[k] = copy(policy[k])
    return out


# ---------------------------------------------------------------- reservations

def res_view(state, rec):
    rest = state["restaurants"][rec["restaurant_id"]]
    tz = tz_of(rest)
    start, end = interval(state, rec)
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
        "revision": rec["revision"],
        "accepted_terms": copy(rec["terms"]),
    }
    if len(rec["table_ids"]) == 1:
        out["table_id"] = rec["table_ids"][0]
    return out


def interval(state, rec):
    s = dt.datetime.fromisoformat(rec["start_utc"])
    return s, s + dt.timedelta(minutes=rec["terms"]["reservation_duration_minutes"])


def overlaps(a, b):
    return a[0] < b[1] and b[0] < a[1]


def hours_for(policy, date):
    wd = WEEKDAYS[date.weekday()]
    return [h for h in policy["opening_hours"] if h.get("weekday") == wd]


def check_slot(rest, policy, naive):
    """Validate a local start time against opening hours, grid and DST; return start UTC."""
    try:
        return _check_slot(rest, policy, naive)
    except (OverflowError, ValueError):
        raise bad("validation_failed", "local time is out of the supported range")


def _check_slot(rest, policy, naive):
    tz = tz_of(rest)
    start = resolve_local(naive, tz)
    if start is None:
        raise bad("invalid_local_time", "local time does not exist")
    minute = naive.hour * 60 + naive.minute
    dur = dt.timedelta(minutes=policy["reservation_duration_minutes"])
    for h in hours_for(policy, naive.date()):
        o, c = parse_hhmm(h["opens"]), parse_hhmm(h["closes"])
        if o <= minute < c:
            if (minute - o) % policy["slot_minutes"] != 0:
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
    """Full booking validation under the policy for the start date.

    Returns (rest, start_utc, ordered table ids, accepted terms)."""
    rest = state["restaurants"].get(rest_id)
    if rest is None:
        raise not_found("unknown restaurant")
    if any(table_of(rest, t) is None for t in table_ids):
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
    policy = select_policy(state, rest, naive.date())
    start = check_slot(rest, policy, naive)
    if party > sum(policy["capacities"][t] for t in table_ids):
        raise bad("party_exceeds_capacity", "party exceeds table capacity")
    return rest, start, list(table_ids), terms_of(policy)


def closed(state, rest_id, table_id, iv):
    """True when an applied closure covers table_id for part of the interval iv."""
    for c in state["meta"][rest_id].get("closures", []):
        if c["table_id"] == table_id and overlaps(iv, (dt.datetime.fromisoformat(c["from_utc"]),
                                                       dt.datetime.fromisoformat(c["to_utc"]))):
            return True
    return False


def bump_restaurant(rest_id):
    STATE["meta"][rest_id]["revision"] += 1


def conflicts(state, rest, table_ids, start, minutes, exclude=()):
    iv = (start, start + dt.timedelta(minutes=minutes))
    if any(closed(state, rest["id"], t, iv) for t in table_ids):
        return True
    for rec in state["reservations"].values():
        if rec["status"] != "confirmed" or rec["id"] in exclude:
            continue
        if rec["restaurant_id"] != rest["id"] or not set(rec["table_ids"]) & set(table_ids):
            continue
        if overlaps(iv, interval(state, rec)):
            return True
    return False


# ---------------------------------------------------------------- history

def table_change(old, new):
    if old is not None and len(old) == 1 and len(new) == 1:
        return {"field": "table_id", "from": old[0], "to": new[0]}
    if old is None and len(new) == 1:
        return {"field": "table_id", "from": None, "to": new[0]}
    return {"field": "table_ids", "from": None if old is None else list(old), "to": list(new)}


def add_history(rec, event, changes, at=None):
    rec["history"].append({"seq": len(rec["history"]) + 1, "at": at or now_iso(), "event": event,
                           "changes": changes, "revision": rec["revision"],
                           "accepted_terms": copy(rec["terms"])})


def created_changes(rec):
    return [table_change(None, rec["table_ids"]),
            {"field": "starts_at_local", "from": None, "to": rec["starts_at_local"]},
            {"field": "party_size", "from": None, "to": rec["party_size"]}]


def apply_change(state, rec, table, local, party, start, terms, mark_exception=True):
    """Commit a real amendment: new terms, one revision, one history entry, series exception."""
    changes = []
    if sorted(table) != sorted(rec["table_ids"]):
        changes.append(table_change(rec["table_ids"], table))
    if local != rec["starts_at_local"]:
        changes.append({"field": "starts_at_local", "from": rec["starts_at_local"], "to": local})
    if party != rec["party_size"]:
        changes.append({"field": "party_size", "from": rec["party_size"], "to": party})
    rec.update(table_ids=list(table), starts_at_local=local, party_size=party, start_utc=start, terms=terms)
    rec["revision"] += 1
    add_history(rec, "changed", changes)
    sid = rec.get("series_id")
    if sid and sid in state["series"]:
        for occ in state["series"][sid]["occurrences"]:
            if occ["reservation_id"] == rec["id"] and mark_exception:
                occ["exception"] = True
        return sid
    return None


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
            managers = r.get("manager_user_ids") or []
            if not isinstance(managers, list) or not all(isinstance(m, str) for m in managers):
                raise bad("validation_failed", "manager_user_ids must be a list of user ids")
            rest = {**r, "tables": tables, "opening_hours": hours, "combinable": combinable,
                    "manager_user_ids": list(managers)}
            for k in ("slot_minutes", "reservation_duration_minutes", "cancellation_cutoff_minutes"):
                if isinstance(rest[k], bool) or not isinstance(rest[k], int):
                    raise bad()
            if rest["slot_minutes"] < 1 or rest["reservation_duration_minutes"] < 1:
                raise bad()
            st["restaurants"][rid] = rest
            st["meta"][rid] = {"policies": [], "revision": 0, "closures": []}
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
            rec = {
                "id": rid, "reference": ref, "user_id": b.get("user_id"),
                "restaurant_id": rest["id"], "table_ids": tids,
                "party_size": b.get("party_size"), "status": b.get("status", "confirmed"),
                "starts_at_local": fmt_local(naive), "start_utc": iso(start),
                "created_at": b.get("created_at") or now_iso(),
                "revision": 1, "terms": terms_of(policy_zero(rest)), "history": [], "series_id": None,
            }
            add_history(rec, "created", created_changes(rec), at=rec["created_at"])
            st["reservations"][rid] = rec
            st["refs"][ref] = rid
    except ApiError:
        raise
    except Exception as e:
        raise bad("validation_failed", "invalid fixture: %s" % e)
    return st


def validate_state(st):
    """Check an imported state object (stage 1, 2 or 3 export); upgrade it in place."""
    keys = ("users", "emails", "tokens", "restaurants", "reservations", "refs", "idem", "seq")
    if not isinstance(st, dict) or any(k not in st for k in keys):
        raise ValueError("missing keys")
    st.setdefault("meta", {})
    st.setdefault("series", {})
    st.setdefault("plans", {})
    for k in keys[:-1] + ("meta", "series"):
        if not isinstance(st[k], dict):
            raise ValueError("bad %s" % k)
    if isinstance(st["seq"], bool) or not isinstance(st["seq"], int):
        raise ValueError("bad seq")
    for u in st["users"].values():
        for f in ("id", "email", "display_name", "pw_hash"):
            if not isinstance(u.get(f), str):
                raise ValueError("bad user")
    for rid, r in st["restaurants"].items():
        r.setdefault("combinable", [])
        r.setdefault("manager_user_ids", [])
        if not isinstance(r["combinable"], list) or not isinstance(r["manager_user_ids"], list):
            raise ValueError("bad restaurant")
        ZoneInfo(r["timezone"])
        for f in ("slot_minutes", "reservation_duration_minutes", "cancellation_cutoff_minutes"):
            if not isinstance(r[f], int):
                raise ValueError("bad restaurant")
        if not isinstance(r["tables"], list) or not isinstance(r["opening_hours"], list):
            raise ValueError("bad restaurant")
        meta = st["meta"].setdefault(rid, {"policies": [], "revision": 0})
        meta.setdefault("closures", [])
        for c in meta["closures"]:
            dt.datetime.fromisoformat(c["from_utc"]), dt.datetime.fromisoformat(c["to_utc"])
        if not isinstance(meta.get("policies"), list) or not isinstance(meta.get("revision"), int):
            raise ValueError("bad meta")
        for p in meta["policies"]:
            parse_date(p["effective_from"])
            for k in TERM_FIELDS + ("policy_version",):
                if k not in p:
                    raise ValueError("bad policy")
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
        if "terms" not in rec:  # stage-1/2 export: policy 0, revision 1, synthesised creation
            rec["terms"] = terms_of(policy_zero(st["restaurants"][rec["restaurant_id"]]))
            rec["revision"] = 1
            rec["history"] = []
            add_history(rec, "created", created_changes(rec), at=rec["created_at"])
            if rec["status"] == "cancelled":
                rec["revision"] = 2
                add_history(rec, "cancelled", [], at=rec["created_at"])
        rec.setdefault("series_id", None)
        if not isinstance(rec["terms"], dict) or not isinstance(rec.get("revision"), int) \
                or not isinstance(rec.get("history"), list):
            raise ValueError("bad reservation")
        int(rec["terms"]["reservation_duration_minutes"])
    for s in st["series"].values():
        for occ in s["occurrences"]:
            if occ["reservation_id"] not in st["reservations"]:
                raise ValueError("bad series")
            occ.setdefault("scheduled_date", st["reservations"][occ["reservation_id"]]["starts_at_local"][:10])
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


def bearer(headers):
    """The user id for a valid bearer token, or None."""
    h = headers.get("Authorization") or ""
    parts = h.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    with LOCK:
        uid = STATE["tokens"].get(parts[1].strip())
        return uid if uid in STATE["users"] else None


def authenticate(headers):
    uid = bearer(headers)
    if uid is None:
        raise ApiError(401, "unauthenticated", "missing, malformed or unknown bearer token")
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
        return 200, copy(r)


# ---------------------------------------------------------------- policies API

def int_in(v, lo, hi):
    return not isinstance(v, bool) and isinstance(v, int) and lo <= v <= hi


def validate_policy(rest, body):
    def fail(msg):
        raise bad("validation_failed", msg)
    for k in ("effective_from",) + TERM_FIELDS:
        if k not in body:
            fail("%s is required" % k)
    try:
        parse_date(body["effective_from"])
    except (ValueError, TypeError):
        fail("effective_from must be a YYYY-MM-DD date")
    if not int_in(body["slot_minutes"], 1, 1440) or not int_in(body["reservation_duration_minutes"], 1, 1440):
        fail("slot_minutes and reservation_duration_minutes must be integers 1..1440")
    if not int_in(body["cancellation_cutoff_minutes"], 0, 10080):
        fail("cancellation_cutoff_minutes must be an integer 0..10080")
    hours = body["opening_hours"]
    if not isinstance(hours, list):
        fail("opening_hours must be a list")
    seen, clean = set(), []
    for h in hours:
        if not isinstance(h, dict) or h.get("weekday") not in WEEKDAYS or h["weekday"] in seen:
            fail("opening_hours needs distinct weekdays mon..sun")
        try:
            if parse_hhmm(h.get("opens")) >= parse_hhmm(h.get("closes")):
                fail("closes must be later than opens")
        except ValueError:
            fail("opens and closes must be HH:MM")
        seen.add(h["weekday"])
        clean.append({"weekday": h["weekday"], "opens": h["opens"], "closes": h["closes"]})
    caps = body["capacities"]
    if not isinstance(caps, dict) or set(caps) != {t["id"] for t in rest["tables"]} \
            or not all(int_in(v, 1, 100) for v in caps.values()):
        fail("capacities must name exactly the restaurant's tables with integers 1..100")
    return {"effective_from": body["effective_from"],
            "slot_minutes": body["slot_minutes"],
            "reservation_duration_minutes": body["reservation_duration_minutes"],
            "cancellation_cutoff_minutes": body["cancellation_cutoff_minutes"],
            "opening_hours": clean,
            "capacities": {t["id"]: caps[t["id"]] for t in rest["tables"]}}


def h_publish_policy(uid, rid, body):
    rest = STATE["restaurants"].get(rid)
    if rest is None:
        raise not_found("unknown restaurant")
    if uid not in rest.get("manager_user_ids", []):
        raise ApiError(403, "forbidden", "only the restaurant's managers may publish policies")
    policy = validate_policy(rest, body)
    meta = STATE["meta"][rid]
    policy["policy_version"] = len(meta["policies"]) + 1
    meta["policies"].append(policy)
    bump_restaurant(rid)
    return 201, copy(policy)


def h_list_policies(rid):
    with LOCK:
        if rid not in STATE["restaurants"]:
            raise not_found("unknown restaurant")
        return 200, {"policies": copy(STATE["meta"][rid]["policies"])}


# ---------------------------------------------------------------- availability

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
    explain = "explain" in q
    if explain and q["explain"] != "true":
        raise bad("validation_failed", "explain only accepts true")
    with LOCK:
        rest = STATE["restaurants"].get(q["restaurant_id"])
        if rest is None:
            raise not_found("unknown restaurant")
        try:
            return _availability(rest, date, party, explain)
        except (OverflowError, ValueError):
            raise bad("validation_failed", "date is out of the supported range")


def _availability(rest, date, party, explain):
    tz = tz_of(rest)
    policy = select_policy(STATE, rest, date)
    dur = dt.timedelta(minutes=policy["reservation_duration_minutes"])
    cap = policy["capacities"]
    busy = {}
    for rec in STATE["reservations"].values():
        if rec["status"] == "confirmed" and rec["restaurant_id"] == rest["id"]:
            for tid in rec["table_ids"]:
                busy.setdefault(tid, []).append(interval(STATE, rec))
    slots, seen = [], set()
    for h in hours_for(policy, date):
        o, c = parse_hhmm(h["opens"]), parse_hhmm(h["closes"])
        close_utc = local_minutes_to_naive(date, c).replace(tzinfo=tz, fold=0).astimezone(UTC)
        m = o
        while m < c:
            naive = local_minutes_to_naive(date, m)
            m += policy["slot_minutes"]
            if naive.date() != date:
                break
            start = resolve_local(naive, tz)
            if start is None or start + dur > close_utc or naive in seen:
                continue
            seen.add(naive)
            iv = (start, start + dur)
            free = {t["id"] for t in rest["tables"]
                    if not any(overlaps(iv, b) for b in busy.get(t["id"], ()))
                    and not closed(STATE, rest["id"], t["id"], iv)}
            avail = [t["id"] for t in rest["tables"] if cap[t["id"]] >= party and t["id"] in free]
            options = [{"table_ids": [tid], "capacity": cap[tid]} for tid in avail]
            for pair in rest.get("combinable") or []:
                total = cap[pair[0]] + cap[pair[1]]
                if total >= party and pair[0] in free and pair[1] in free:
                    options.append({"table_ids": list(pair), "capacity": total})
            slot = {"starts_at_local": fmt_local(naive),
                    "starts_at": iso(start.astimezone(tz)),
                    "available_table_ids": avail,
                    "available_options": options}
            if explain:
                slot["explain"] = []
                for t in rest["tables"]:
                    fits, clear_ = cap[t["id"]] >= party, t["id"] in free
                    slot["explain"].append({
                        "table_id": t["id"], "policy_version": policy["policy_version"],
                        "available": fits and clear_,
                        "rules": [{"rule": "capacity", "holds": fits},
                                  {"rule": "no_overlap", "holds": clear_}]})
            slots.append(slot)
    slots.sort(key=lambda s: s["starts_at_local"])
    return 200, {"restaurant_id": rest["id"], "date": date.isoformat(),
                 "timezone": rest["timezone"], "slots": slots}


# ---------------------------------------------------------------- reservations API

def new_record(uid, rest, table_ids, local, party, start, terms):
    rid = next_id(STATE, "res")
    while rid in STATE["reservations"]:
        rid = next_id(STATE, "res")
    ref = new_reference(STATE)
    rec = {"id": rid, "reference": ref, "user_id": uid, "restaurant_id": rest["id"],
           "table_ids": table_ids, "party_size": party, "status": "confirmed",
           "starts_at_local": local, "start_utc": iso(start), "created_at": now_iso(),
           "revision": 1, "terms": terms, "history": [], "series_id": None}
    add_history(rec, "created", created_changes(rec), at=rec["created_at"])
    return rec


def store(rec):
    STATE["reservations"][rec["id"]] = rec
    STATE["refs"][rec["reference"]] = rec["id"]


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
    rest, start, table_ids, terms = validate_booking(STATE, rest_id, table_ids, body["starts_at_local"], party)
    if conflicts(STATE, rest, table_ids, start, terms["reservation_duration_minutes"]):
        raise ApiError(409, "table_unavailable", "table is taken for that time")
    rec = new_record(uid, rest, table_ids, body["starts_at_local"], party, start, terms)
    store(rec)
    bump_restaurant(rest["id"])
    return 201, res_view(STATE, rec)


def own_reservation(uid, ref):
    rid = STATE["refs"].get(ref)
    rec = STATE["reservations"].get(rid) if rid else None
    if uid is None or rec is None or rec["user_id"] != uid:
        raise not_found("no such reservation")
    return rec


def check_cutoff(rec):
    start = dt.datetime.fromisoformat(rec["start_utc"])
    if now_utc() >= start - dt.timedelta(minutes=rec["terms"]["cancellation_cutoff_minutes"]):
        raise ApiError(409, "cutoff_passed", "too close to the reservation start")


def h_list(uid):
    with LOCK:
        mine = [r for r in STATE["reservations"].values() if r["user_id"] == uid]
        mine.sort(key=lambda r: (dt.datetime.fromisoformat(r["start_utc"]), r["created_at"]), reverse=True)
        return 200, {"reservations": [res_view(STATE, r) for r in mine]}


def h_get(uid, ref):
    with LOCK:
        return 200, res_view(STATE, own_reservation(uid, ref))


def h_history(uid, ref):
    with LOCK:
        rec = own_reservation(uid, ref)
        return 200, {"reference": rec["reference"], "entries": copy(rec["history"])}


def h_decision(uid, ref):
    with LOCK:
        rec = own_reservation(uid, ref)
        return 200, {"reference": rec["reference"], "revision": rec["revision"],
                     "accepted_terms": copy(rec["terms"])}


def bump_series(sid):
    if sid and sid in STATE["series"]:
        STATE["series"][sid]["revision"] += 1


def h_cancel(uid, ref):
    with LOCK:
        rec = own_reservation(uid, ref)
        if rec["status"] == "cancelled":
            return 200, res_view(STATE, rec)
        check_cutoff(rec)
        rec["status"] = "cancelled"
        rec["revision"] += 1
        add_history(rec, "cancelled", [])
        bump_restaurant(rec["restaurant_id"])
        bump_series(rec.get("series_id"))
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
    if item.get("expected_revision") is not None:
        if not int_in(item["expected_revision"], 1, 2 ** 63):
            raise bad("validation_failed", "expected_revision must be a positive integer")
        out["expected_revision"] = item["expected_revision"]
    return out


def check_editable(rec, fields):
    """Stale revision, cancellation and accepted-cutoff checks, in that order."""
    if "expected_revision" in fields and fields["expected_revision"] != rec["revision"]:
        raise ApiError(409, "stale_revision", "the reservation has changed since that revision")
    if rec["status"] == "cancelled":
        raise ApiError(409, "reservation_cancelled", "reservation is cancelled")
    check_cutoff(rec)


def plan_change(rec, fields):
    """Validate an amendment; return (table, local, party, start_utc, terms) or None for a no-op."""
    table = fields.get("table_ids", rec["table_ids"])
    local = fields.get("starts_at_local", rec["starts_at_local"])
    party = fields.get("party_size", rec["party_size"])
    if "party_size" in fields:
        check_party(party)
    if (sorted(table), local, party) == (sorted(rec["table_ids"]), rec["starts_at_local"], rec["party_size"]) \
            and not isinstance(party, bool):
        return None
    _, start, table, terms = validate_booking(STATE, rec["restaurant_id"], table, local, party)
    return table, local, party, iso(start), terms


def h_patch(uid, ref, body):
    fields = item_fields(body)
    with LOCK:
        rec = own_reservation(uid, ref)
        check_editable(rec, fields)
        change = plan_change(rec, fields)
        if change is None:
            return 200, res_view(STATE, rec)
        table, local, party, start, terms = change
        rest = STATE["restaurants"][rec["restaurant_id"]]
        if conflicts(STATE, rest, table, dt.datetime.fromisoformat(start),
                     terms["reservation_duration_minutes"], exclude=(rec["id"],)):
            raise ApiError(409, "table_unavailable", "table is taken for that time")
        bump_series(apply_change(STATE, rec, table, local, party, start, terms))
        bump_restaurant(rec["restaurant_id"])
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
        check_editable(rec, fields)
        recs.append(rec)
        plans.append(plan_change(rec, fields))
    rest = STATE["restaurants"][rest_id]
    listed = {r["id"] for r in recs}
    results = []
    for rec, plan in zip(recs, plans):
        if plan is None:
            results.append((rec["table_ids"], interval(STATE, rec)))
        else:
            s = dt.datetime.fromisoformat(plan[3])
            results.append((plan[0], (s, s + dt.timedelta(minutes=plan[4]["reservation_duration_minutes"]))))
    for i in range(len(results)):
        for j in range(i + 1, len(results)):
            if set(results[i][0]) & set(results[j][0]) and overlaps(results[i][1], results[j][1]):
                raise ApiError(409, "table_unavailable", "moved bookings overlap")
        minutes = (results[i][1][1] - results[i][1][0]).total_seconds() // 60
        if conflicts(STATE, rest, results[i][0], results[i][1][0], minutes, exclude=listed):
            raise ApiError(409, "table_unavailable", "table is taken for that time")
    touched = set()
    for rec, plan in zip(recs, plans):
        if plan is not None:
            sid = apply_change(STATE, rec, *plan)
            if sid:
                touched.add(sid)
    for sid in touched:
        bump_series(sid)
    if any(plan is not None for plan in plans):
        bump_restaurant(rest_id)
    return 201, {"reservations": [res_view(STATE, r) for r in recs]}


# ---------------------------------------------------------------- series

def series_view(s):
    occs = []
    for occ in s["occurrences"]:
        rec = STATE["reservations"][occ["reservation_id"]]
        occs.append({"index": occ["index"], "reference": rec["reference"], "exception": occ["exception"],
                     "reservation": res_view(STATE, rec)})
    return {"series_id": s["id"], "revision": s["revision"], "interval_weeks": s["interval_weeks"],
            "occurrences": occs}


def h_create_series(uid, body):
    ref = body.get("anchor_reference")
    if not isinstance(ref, str):
        raise bad("validation_failed", "anchor_reference is required")
    count, weeks = body.get("count"), body.get("interval_weeks")
    if not int_in(count, 2, 12):
        raise bad("validation_failed", "count must be an integer 2..12")
    if not int_in(weeks, 1, 4):
        raise bad("validation_failed", "interval_weeks must be an integer 1..4")
    anchor = own_reservation(uid, ref)
    if anchor["status"] == "cancelled":
        raise ApiError(409, "reservation_cancelled", "reservation is cancelled")
    if anchor.get("series_id"):
        raise ApiError(409, "already_in_series", "reservation already belongs to a series")
    check_cutoff(anchor)
    rest = STATE["restaurants"][anchor["restaurant_id"]]
    base = parse_local(anchor["starts_at_local"])
    planned = []
    for i in range(1, count):
        try:
            naive = base + dt.timedelta(days=7 * weeks * i)
        except OverflowError:
            raise bad("validation_failed", "occurrence date is out of the supported range")
        local = fmt_local(naive)
        _, start, table_ids, terms = validate_booking(STATE, rest["id"], list(anchor["table_ids"]), local,
                                                      anchor["party_size"])
        minutes = terms["reservation_duration_minutes"]
        iv = (start, start + dt.timedelta(minutes=minutes))
        if conflicts(STATE, rest, table_ids, start, minutes) or any(
                set(p[1]) & set(table_ids) and overlaps(p[4], iv) for p in planned):
            raise ApiError(409, "table_unavailable", "table is taken for occurrence %d" % i)
        planned.append((local, table_ids, start, terms, iv))
    sid = next_id(STATE, "ser")
    series = {"id": sid, "user_id": uid, "restaurant_id": rest["id"], "revision": 1,
              "interval_weeks": weeks,
              "occurrences": [{"index": 0, "reservation_id": anchor["id"], "exception": False,
                               "scheduled_date": anchor["starts_at_local"][:10]}]}
    for i, (local, table_ids, start, terms, _) in enumerate(planned, start=1):
        rec = new_record(uid, rest, table_ids, local, anchor["party_size"], start, terms)
        rec["series_id"] = sid
        store(rec)
        series["occurrences"].append({"index": i, "reservation_id": rec["id"], "exception": False,
                                      "scheduled_date": local[:10]})
    anchor["series_id"] = sid
    STATE["series"][sid] = series
    bump_restaurant(rest["id"])
    return 201, series_view(series)


def h_get_series(uid, sid):
    with LOCK:
        s = STATE["series"].get(sid)
        if uid is None or s is None or s["user_id"] != uid:
            raise not_found("no such series")
        return 200, series_view(s)


HHMM_STRICT = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")


def h_amend_series(uid, sid, body):
    s = STATE["series"].get(sid)
    if s is None or s["user_id"] != uid:
        raise not_found("no such series")
    exp, start_idx, clock = body.get("expected_revision"), body.get("from_index"), body.get("local_time")
    if not int_in(exp, 1, 2 ** 63):
        raise bad("validation_failed", "expected_revision must be a positive integer")
    if not int_in(start_idx, 0, len(s["occurrences"]) - 1):
        raise bad("validation_failed", "from_index is out of range")
    if not isinstance(clock, str) or not HHMM_STRICT.match(clock):
        raise bad("validation_failed", "local_time must be HH:MM")
    if exp != s["revision"]:
        raise ApiError(409, "stale_revision", "the series has changed since that revision")
    rest = STATE["restaurants"][s["restaurant_id"]]
    changes = []  # (rec, plan) in index order
    for occ in s["occurrences"]:
        rec = STATE["reservations"][occ["reservation_id"]]
        if occ["index"] < start_idx or occ["exception"] or rec["status"] != "confirmed":
            continue
        local = occ["scheduled_date"] + "T" + clock
        if local == rec["starts_at_local"]:
            continue  # no-op keeps its terms
        check_cutoff(rec)
        _, start, table_ids, terms = validate_booking(STATE, rest["id"], list(rec["table_ids"]), local,
                                                      rec["party_size"])
        changes.append((rec, (table_ids, local, rec["party_size"], iso(start), terms)))
    moving = {rec["id"] for rec, _ in changes}
    ivs = []
    for rec, plan in changes:
        st = dt.datetime.fromisoformat(plan[3])
        minutes = plan[4]["reservation_duration_minutes"]
        iv = (st, st + dt.timedelta(minutes=minutes))
        if conflicts(STATE, rest, plan[0], st, minutes, exclude=moving) or any(
                set(t) & set(plan[0]) and overlaps(other, iv) for t, other in ivs):
            raise ApiError(409, "table_unavailable", "an amended occurrence conflicts")
        ivs.append((plan[0], iv))
    for rec, plan in changes:
        apply_change(STATE, rec, *plan, mark_exception=False)
    if changes:
        s["revision"] += 1
        bump_restaurant(rest["id"])
    return 201, series_view(s)


# ---------------------------------------------------------------- seating changes

def parse_instant(v):
    if not isinstance(v, str) or "T" not in v:
        raise ValueError("not an instant")
    d = dt.datetime.fromisoformat(v)
    if d.tzinfo is None:
        raise ValueError("instant needs an explicit offset")
    return d.astimezone(UTC)


def seating_options(rest):
    """Singles in fixture order then declared pairs; the list index is the option rank."""
    return [[t["id"]] for t in rest["tables"]] + [list(p) for p in rest.get("combinable") or []]


def h_preview_replan(uid, rest, body):
    table_id = body.get("table_id")
    try:
        f, t = parse_instant(body.get("from")), parse_instant(body.get("to"))
    except (ValueError, TypeError):
        raise bad("validation_failed", "from and to must be RFC 3339 instants with offsets")
    if not f < t:
        raise bad("validation_failed", "from must be earlier than to")
    if not isinstance(table_id, str):
        raise bad("validation_failed", "table_id is required")
    if table_of(rest, table_id) is None:
        raise not_found("unknown table")
    closure_iv = (f, t)
    considered = sorted((r for r in STATE["reservations"].values()
                         if r["status"] == "confirmed" and r["restaurant_id"] == rest["id"]
                         and overlaps(interval(STATE, r), closure_iv)), key=lambda r: r["reference"])
    options = seating_options(rest)
    if len(rest["tables"]) > 6 or len(rest.get("combinable") or []) > 4 or len(considered) > 6:
        raise bad("planning_limit", "too many tables, pairs or bookings to plan")
    ids = {r["id"] for r in considered}
    fixed = [r for r in STATE["reservations"].values()
             if r["status"] == "confirmed" and r["restaurant_id"] == rest["id"] and r["id"] not in ids]
    cands = []  # per booking: [(rank, table_ids, changed, unused)]
    for r in considered:
        iv = interval(STATE, r)
        caps = r["terms"]["capacities"]
        mine = []
        for rank, opt in enumerate(options):
            cap = sum(caps.get(x, 0) for x in opt)
            if cap < r["party_size"] or (table_id in opt):
                continue
            if any(closed(STATE, rest["id"], x, iv) for x in opt):
                continue
            if any(set(fx["table_ids"]) & set(opt) and overlaps(iv, interval(STATE, fx)) for fx in fixed):
                continue
            mine.append((rank, opt, sorted(opt) != sorted(r["table_ids"]), cap - r["party_size"]))
        cands.append((r, iv, mine))
    best = [None, None]  # (changed, unused), choice list

    def search(i, chosen, changed, unused):
        if best[0] is not None and (changed, unused) >= best[0]:
            return
        if i == len(cands):
            best[0], best[1] = (changed, unused), list(chosen)
            return
        r, iv, mine = cands[i]
        for c in mine:
            if any(set(c[1]) & set(o[1]) and overlaps(iv, cands[j][1]) for j, o in enumerate(chosen)):
                continue
            chosen.append(c)
            search(i + 1, chosen, changed + c[2], unused + c[3])
            chosen.pop()

    search(0, [], 0, 0)
    if best[1] is None:
        raise ApiError(409, "no_feasible_plan", "no seating arrangement satisfies the closure")
    pid = "plan_" + secrets.token_hex(8)
    assignments = [{"reference": r["reference"], "table_ids": list(c[1]), "changed": c[2]}
                   for (r, _, _), c in zip(cands, best[1])]
    response = {"plan_id": pid, "restaurant_revision": STATE["meta"][rest["id"]]["revision"],
                "closure": {"table_id": table_id, "from": body["from"], "to": body["to"]},
                "assignments": assignments, "moved_count": best[0][0], "unused_seats": best[0][1]}
    STATE["plans"][pid] = {"id": pid, "restaurant_id": rest["id"], "user_id": uid,
                           "revision": STATE["meta"][rest["id"]]["revision"],
                           "closure": {"table_id": table_id, "from_utc": iso(f), "to_utc": iso(t)},
                           "assignments": [{"reservation_id": r["id"], "table_ids": list(c[1])}
                                           for (r, _, _), c in zip(cands, best[1])],
                           "applied_key": None}
    return 201, copy(response)


def h_apply_replan(rest, pid, key):
    plan = STATE["plans"].get(pid)
    if plan is None or plan["restaurant_id"] != rest["id"]:
        raise not_found("no such plan")
    if plan["applied_key"] is not None and plan["applied_key"] != key:
        raise ApiError(409, "plan_already_applied", "this plan has already been applied")
    meta = STATE["meta"][rest["id"]]
    if meta["revision"] != plan["revision"]:
        raise ApiError(409, "stale_plan", "the restaurant changed after this plan was previewed")
    meta["closures"].append(dict(plan["closure"], plan_id=pid))
    touched = set()
    recs = []
    for a in plan["assignments"]:
        rec = STATE["reservations"][a["reservation_id"]]
        recs.append(rec)
        if sorted(a["table_ids"]) != sorted(rec["table_ids"]):
            old = list(rec["table_ids"])
            rec["table_ids"] = list(a["table_ids"])
            rec["revision"] += 1
            add_history(rec, "reassigned", [{"field": "table_ids", "from": old, "to": list(a["table_ids"])}])
            rec["history"][-1]["plan_id"] = pid
            if rec.get("series_id") in STATE["series"]:
                touched.add(rec["series_id"])
    for sid in touched:
        bump_series(sid)
    bump_restaurant(rest["id"])
    plan["applied_key"] = key
    recs.sort(key=lambda r: r["reference"])
    return 201, {"plan_id": pid, "restaurant_revision": meta["revision"],
                 "reservations": [res_view(STATE, r) for r in recs]}


def manager_restaurant(uid, rid):
    rest = STATE["restaurants"].get(rid)
    if rest is None:
        raise not_found("unknown restaurant")
    if uid not in rest.get("manager_user_ids", []):
        raise ApiError(403, "forbidden", "only the restaurant's managers may do this")
    return rest


def h_reset(body):
    global STATE
    st = build_from_fixture(body)
    with LOCK:
        STATE = st
    return 204, None


def h_export():
    with LOCK:
        snap = copy(STATE)
    return 200, {"track": "tablekeeper", "format_version": 1, "state": snap}


def h_import(body):
    global STATE
    if body.get("track") != "tablekeeper":
        raise bad("validation_failed", "wrong track")
    v = body.get("format_version")
    if isinstance(v, bool) or v != 1:
        raise bad("validation_failed", "wrong format_version")
    try:
        st = validate_state(copy(body.get("state")))
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
            if len(seg) == 3 and seg[0] == "reservations" and seg[2] == "history":
                return h_history(bearer(h), seg[1])
            if len(seg) == 3 and seg[0] == "reservations" and seg[2] == "decision":
                return h_decision(bearer(h), seg[1])
            if len(seg) == 3 and seg[0] == "restaurants" and seg[2] == "policies":
                return h_list_policies(seg[1])
            if len(seg) == 2 and seg[0] == "series":
                return h_get_series(bearer(h), seg[1])
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
            if path == "/series" or (len(seg) == 3 and seg[0] == "restaurants" and seg[2] == "policies"):
                uid = authenticate(h)
                body = parse_object(raw)
                key = idem_key(h)
                if path == "/series":
                    fn = lambda: h_create_series(uid, body)
                else:
                    fn = lambda: h_publish_policy(uid, seg[1], body)
                return with_idempotency(uid, method, path, key, body, fn)
            if len(seg) == 3 and seg[0] == "series" and seg[2] == "amend":
                uid = authenticate(h)
                body = parse_object(raw)
                key = idem_key(h)
                return with_idempotency(uid, method, path, key, body, lambda: h_amend_series(uid, seg[1], body))
            if (len(seg) == 3 and seg[0] == "restaurants" and seg[2] == "replans") or \
                    (len(seg) == 5 and seg[0] == "restaurants" and seg[2] == "replans" and seg[4] == "apply"):
                uid = authenticate(h)
                with LOCK:
                    manager_restaurant(uid, seg[1])
                body = parse_object(raw)
                key = idem_key(h)
                if len(seg) == 3:
                    fn = lambda: h_preview_replan(uid, manager_restaurant(uid, seg[1]), body)
                else:
                    fn = lambda: h_apply_replan(manager_restaurant(uid, seg[1]), seg[3], key)
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
