"""Black-box tests for the stage-1 service. Run: BASE=http://localhost:8080 python3 tests/test_api.py"""
import datetime as dt
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

BASE = os.environ.get("BASE", "http://localhost:8080")
WD = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def call(method, path, body=None, token=None, key=None, raw=None):
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if key is not None:
        req.add_header("Idempotency-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            txt = r.read()
            return r.status, (json.loads(txt) if txt else None)
    except urllib.error.HTTPError as e:
        txt = e.read()
        return e.code, (json.loads(txt) if txt else None)


def err(resp, status, code):
    assert resp[0] == status and resp[1]["error"]["code"] == code, (status, code, resp)


def day(lead=7, tz="Europe/Berlin"):
    return (dt.datetime.now(ZoneInfo(tz)).date() + dt.timedelta(days=lead)).isoformat()


def restaurant(rid="r_anker", tz="Europe/Berlin", opens="18:00", closes="23:00", cutoff=120):
    return {"id": rid, "name": rid, "timezone": tz, "slot_minutes": 30,
            "reservation_duration_minutes": 90, "cancellation_cutoff_minutes": cutoff,
            "opening_hours": [{"weekday": w, "opens": opens, "closes": closes} for w in WD],
            "tables": [{"id": "t_1", "label": "1", "capacity": 2},
                       {"id": "t_2", "label": "2", "capacity": 4},
                       {"id": "t_3", "label": "3", "capacity": 6}]}


USERS = [{"id": "u_ada", "email": "ada@example.com", "password": "correct horse", "display_name": "Ada"},
         {"id": "u_bob", "email": "bob@example.com", "password": "correct horse", "display_name": "Bob"}]


def reset(rests=None, reservations=None):
    s = call("POST", "/_test/reset", {"users": USERS, "restaurants": rests or [restaurant()],
                                      "reservations": reservations or []})
    assert s[0] == 204, s


def login(email="ada@example.com"):
    s = call("POST", "/auth/login", {"email": email, "password": "correct horse"})
    assert s[0] == 200, s
    return s[1]["token"]


KEYN = [0]


def k():
    KEYN[0] += 1
    return "key-%d" % KEYN[0]


def book(tok, table="t_2", hhmm="19:00", party=2, d=None, rid="r_anker"):
    return call("POST", "/reservations", {"restaurant_id": rid, "table_id": table,
                                          "starts_at_local": "%sT%s" % (d or day(), hhmm),
                                          "party_size": party}, tok, k())


TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


@test
def health_and_errors():
    assert call("GET", "/health") == (200, {"status": "ok"})
    reset()
    err(call("GET", "/reservations"), 401, "unauthenticated")
    err(call("GET", "/reservations", token="nope"), 401, "unauthenticated")
    err(call("GET", "/restaurants/zzz"), 404, "not_found")
    err(call("POST", "/auth/login", raw=b"{nope"), 400, "malformed_request")
    long_id = restaurant("r" * 65)
    s = call("POST", "/_test/reset", {"users": [], "restaurants": [long_id], "reservations": []})
    err(s, 422, "validation_failed")


@test
def auth():
    reset()
    s = call("POST", "/auth/signup", {"email": "c@x.io", "password": "12345678", "display_name": "C", "z": 1})
    assert s[0] == 201 and s[1]["token"], s
    err(call("POST", "/auth/signup", {"email": "c@x.io", "password": "12345678", "display_name": "C"}), 409, "email_taken")
    err(call("POST", "/auth/signup", {"email": "d@x.io", "password": "1234567", "display_name": "D"}), 422, "validation_failed")
    err(call("POST", "/auth/signup", {"email": "dx.io", "password": "12345678", "display_name": "D"}), 422, "validation_failed")
    err(call("POST", "/auth/login", {"email": "c@x.io", "password": "wrongpass"}), 401, "unauthenticated")
    t1, t2 = login(), login()
    assert t1 != t2
    assert call("GET", "/reservations", token=t1)[0] == 200 and call("GET", "/reservations", token=t2)[0] == 200


@test
def availability():
    reset()
    d = day()
    s = call("GET", "/availability?restaurant_id=r_anker&date=%s&party_size=4&x=1" % d)
    assert s[0] == 200
    times = [x["starts_at_local"][-5:] for x in s[1]["slots"]]
    assert times[0] == "18:00" and times[-1] == "21:30", times
    assert s[1]["slots"][0]["available_table_ids"] == ["t_2", "t_3"]
    for bad in ("1e9", "4.0", "+4", "0", "-1", ""):
        err(call("GET", "/availability?restaurant_id=r_anker&date=%s&party_size=%s" % (d, bad)), 422, "validation_failed")
    err(call("GET", "/availability?restaurant_id=r_anker&party_size=2"), 422, "validation_failed")
    err(call("GET", "/availability?restaurant_id=r_anker&date=2026-02-30&party_size=2"), 422, "validation_failed")
    closed = restaurant()
    closed["opening_hours"] = []
    reset([closed])
    assert call("GET", "/availability?restaurant_id=r_anker&date=%s&party_size=2" % d)[1]["slots"] == []


@test
def booking_and_overlap():
    reset()
    ada, bob = login(), login("bob@example.com")
    s = book(ada, hhmm="19:00", party=4)
    assert s[0] == 201 and s[1]["status"] == "confirmed", s
    r = s[1]
    assert 6 <= len(r["reference"]) <= 12 and r["reference"].isalnum() and r["reference"].upper() == r["reference"]
    assert r["ends_at"][11:16] == "20:30"
    err(book(bob, hhmm="20:00"), 409, "table_unavailable")
    assert book(bob, hhmm="20:30")[0] == 201  # half-open
    err(book(bob, hhmm="19:15"), 422, "not_on_slot_grid")
    err(book(bob, hhmm="22:00"), 422, "outside_opening_hours")
    err(book(bob, hhmm="17:00"), 422, "outside_opening_hours")
    err(book(bob, table="t_1", party=3), 422, "party_exceeds_capacity")
    for p in (0, "2", True, 2.5):
        err(book(bob, party=p), 422, "validation_failed")
    err(book(bob, table="t_9"), 404, "not_found")
    err(book(bob, rid="r_none"), 404, "not_found")
    err(call("POST", "/reservations", {"restaurant_id": 5, "table_id": "t_2", "starts_at_local": day() + "T19:00",
                                       "party_size": 2}, bob, k()), 400, "malformed_request")
    err(call("POST", "/reservations", {"restaurant_id": "r_anker", "table_id": "t_2",
                                       "starts_at_local": day() + "T19:00+02:00", "party_size": 2}, bob, k()),
        422, "validation_failed")
    err(call("GET", "/reservations/" + r["reference"], token=bob), 404, "not_found")
    assert call("GET", "/reservations/" + r["reference"], token=ada)[1] == r
    past = book(ada, d=day(-3), hhmm="19:00")
    assert past[0] == 201, past
    lst = call("GET", "/reservations", token=ada)[1]["reservations"]
    assert [x["reference"] for x in lst] == [r["reference"], past[1]["reference"]]


@test
def idempotency():
    reset()
    ada, bob = login(), login("bob@example.com")
    body = {"restaurant_id": "r_anker", "table_id": "t_2", "starts_at_local": day() + "T19:00", "party_size": 2}
    err(call("POST", "/reservations", body, ada), 400, "missing_idempotency_key")
    err(call("POST", "/reservations", body, ada, ""), 400, "missing_idempotency_key")
    err(call("POST", "/reservations", body, ada, "x" * 256), 422, "validation_failed")
    a = call("POST", "/reservations", body, ada, "same")
    b = call("POST", "/reservations", dict(reversed(list(body.items()))), ada, "same")
    assert a[0] == 201 and b == (200, a[1]), (a, b)
    err(call("POST", "/reservations", {"party_size": "bad"}, ada, "same"), 409, "idempotency_key_reuse")
    # other user, same key: independent (and conflicts on the table)
    err(call("POST", "/reservations", body, bob, "same"), 409, "table_unavailable")
    # failed key is reusable
    ok = dict(body, table_id="t_3")
    assert call("POST", "/reservations", ok, bob, "same")[0] == 201
    # replay after cancel returns original
    call("POST", "/reservations/%s/cancel" % a[1]["reference"], token=ada)
    assert call("POST", "/reservations", body, ada, "same") == (200, a[1])
    # concurrent identical
    out = []
    cb = dict(body, starts_at_local=day() + "T21:00")
    ths = [threading.Thread(target=lambda: out.append(call("POST", "/reservations", cb, ada, "conc")))
           for _ in range(20)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    assert sorted(x[0] for x in out) == [200] * 19 + [201], [x[0] for x in out]
    assert len({json.dumps(x[1], sort_keys=True) for x in out}) == 1


@test
def concurrent_no_double_booking():
    reset()
    toks = [login() for _ in range(5)]
    out = []

    def go(i):
        out.append(book(toks[i % 5], hhmm="19:00"))
    ths = [threading.Thread(target=go, args=(i,)) for i in range(40)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    codes = sorted(x[0] for x in out)
    assert codes.count(201) == 1 and codes.count(409) == 39, codes


@test
def cancel_and_patch():
    reset()
    ada = login()
    r = book(ada, hhmm="19:00")[1]
    av = lambda: call("GET", "/availability?restaurant_id=r_anker&date=%s&party_size=2" % day())[1]["slots"]
    assert "t_2" not in av()[2]["available_table_ids"]
    p = call("PATCH", "/reservations/" + r["reference"], {"table_id": "t_3", "starts_at_local": day() + "T20:00"}, ada)
    assert p[0] == 200 and p[1]["reference"] == r["reference"] and p[1]["reservation_id"] == r["reservation_id"], p
    assert "t_2" in av()[2]["available_table_ids"]
    other = book(ada, table="t_1", hhmm="20:00")[1]
    err(call("PATCH", "/reservations/" + r["reference"], {"table_id": "t_1"}, ada), 409, "table_unavailable")
    err(call("PATCH", "/reservations/" + r["reference"], {"party_size": 0}, ada), 422, "validation_failed")
    assert call("GET", "/reservations/" + r["reference"], token=ada)[1] == p[1]
    c = call("POST", "/reservations/%s/cancel" % other["reference"], token=ada)
    assert c[0] == 200 and c[1]["status"] == "cancelled"
    assert call("POST", "/reservations/%s/cancel" % other["reference"], token=ada)[0] == 200
    err(call("PATCH", "/reservations/" + other["reference"], {"party_size": 1}, ada), 409, "reservation_cancelled")
    err(call("POST", "/reservations/%s/cancel" % r["reference"], token=login("bob@example.com")), 404, "not_found")
    # cutoff: booking already started
    past = book(ada, d=day(-1))[1]
    err(call("POST", "/reservations/%s/cancel" % past["reference"], token=ada), 409, "cutoff_passed")
    err(call("PATCH", "/reservations/" + past["reference"], {"party_size": 1}, ada), 409, "cutoff_passed")


@test
def dst():
    reset([restaurant("r_b", opens="00:00", closes="23:30"),
           restaurant("r_ny", tz="America/New_York", opens="00:00", closes="23:30")])
    ada = login()
    sl = lambda rid, d: [x["starts_at_local"][-5:] for x in
                         call("GET", "/availability?restaurant_id=%s&date=%s&party_size=2" % (rid, d))[1]["slots"]]
    assert "02:30" not in sl("r_b", "2026-03-29") and "02:00" not in sl("r_b", "2026-03-29")
    assert sl("r_b", "2026-10-25").count("02:00") == 1
    assert "02:30" not in sl("r_ny", "2026-03-08")
    assert sl("r_ny", "2026-11-01").count("01:30") == 1
    err(book(ada, rid="r_b", d="2026-03-29", hhmm="02:30"), 422, "invalid_local_time")
    s = book(ada, rid="r_b", d="2026-10-25", hhmm="01:30")[1]
    assert s["starts_at"].endswith("+02:00") and s["ends_at"] == "2026-10-25T02:00:00+01:00", s
    s = book(ada, rid="r_ny", d="2026-11-01", hhmm="01:00", table="t_3")[1]
    assert s["starts_at"] == "2026-11-01T01:00:00-04:00" and s["ends_at"] == "2026-11-01T01:30:00-05:00", s


@test
def moves():
    reset()
    ada, bob = login(), login("bob@example.com")
    a = book(ada, table="t_2", hhmm="19:00")[1]
    b = book(ada, table="t_3", hhmm="19:00")[1]
    body = {"moves": [{"reference": a["reference"], "table_id": "t_3"},
                      {"reference": b["reference"], "table_id": "t_2"}]}
    err(call("POST", "/reservation-moves", body), 401, "unauthenticated")
    err(call("POST", "/reservation-moves", body, ada), 400, "missing_idempotency_key")
    s = call("POST", "/reservation-moves", body, ada, "mv1")
    assert s[0] == 201 and [x["table_id"] for x in s[1]["reservations"]] == ["t_3", "t_2"], s
    assert call("POST", "/reservation-moves", body, ada, "mv1") == (200, s[1])
    err(call("POST", "/reservation-moves", {"moves": []}, ada, k()), 422, "validation_failed")
    err(call("POST", "/reservation-moves", {"moves": [{"reference": a["reference"]}] * 2}, ada, k()), 422, "validation_failed")
    err(call("POST", "/reservation-moves", {"moves": [{"reference": "NOPE00"}]}, ada, k()), 404, "not_found")
    err(call("POST", "/reservation-moves", {"moves": [{"reference": a["reference"]}]}, bob, k()), 404, "not_found")
    c = book(ada, table="t_1", hhmm="21:00")[1]
    # conflict with unlisted booking -> nothing changes, key reusable
    bad = {"moves": [{"reference": a["reference"], "starts_at_local": day() + "T21:00"},
                     {"reference": b["reference"], "table_id": "t_1", "starts_at_local": day() + "T20:30"}]}
    err(call("POST", "/reservation-moves", bad, ada, "mv2"), 409, "table_unavailable")
    assert call("GET", "/reservations/" + a["reference"], token=ada)[1]["starts_at_local"].endswith("19:00")
    ok = {"moves": [{"reference": c["reference"]}, {"reference": a["reference"], "party_size": 3}]}
    s2 = call("POST", "/reservation-moves", ok, ada, "mv2")
    assert s2[0] == 201 and s2[1]["reservations"][0] == c and s2[1]["reservations"][1]["party_size"] == 3, s2
    call("POST", "/reservations/%s/cancel" % c["reference"], token=ada)
    err(call("POST", "/reservation-moves", {"moves": [{"reference": c["reference"]}]}, ada, k()), 409, "reservation_cancelled")
    reset([restaurant(), restaurant("r_two")])
    ada = login()
    x, y = book(ada)[1], book(ada, rid="r_two")[1]
    err(call("POST", "/reservation-moves", {"moves": [{"reference": x["reference"]}, {"reference": y["reference"]}]},
             ada, k()), 422, "validation_failed")


@test
def export_import():
    reset()
    ada = login()
    body = {"restaurant_id": "r_anker", "table_id": "t_2", "starts_at_local": day() + "T19:00", "party_size": 2}
    first = call("POST", "/reservations", body, ada, "exp")
    mv = call("POST", "/reservation-moves", {"moves": [{"reference": first[1]["reference"]}]}, ada, "mvexp")
    ex = call("GET", "/_test/export")
    assert ex[0] == 200 and ex[1]["track"] == "tablekeeper" and ex[1]["format_version"] == 1
    book(ada, hhmm="21:00")
    snap = call("GET", "/_test/export")[1]
    assert snap != ex[1]
    reset()
    err(call("POST", "/_test/import", dict(ex[1], track="other")), 422, "validation_failed")
    err(call("POST", "/_test/import", dict(ex[1], format_version=2)), 422, "validation_failed")
    err(call("POST", "/_test/import", {"track": "tablekeeper", "format_version": 1, "state": {"x": 1}}), 422, "validation_failed")
    err(call("GET", "/reservations", token=ada), 401, "unauthenticated")
    for _ in range(2):
        assert call("POST", "/_test/import", ex[1])[0] == 204
    assert call("POST", "/reservations", body, ada, "exp") == (200, first[1])
    assert call("POST", "/reservation-moves", {"moves": [{"reference": first[1]["reference"]}]}, ada, "mvexp") == (200, mv[1])
    assert len(call("GET", "/reservations", token=ada)[1]["reservations"]) == 1
    assert call("POST", "/auth/login", {"email": "ada@example.com", "password": "correct horse"})[0] == 200
    reset()
    err(call("GET", "/reservations", token=ada), 401, "unauthenticated")


@test
def review_cycle1():
    # D1: calendar edges never 5xx
    reset([restaurant("r_b", opens="00:00", closes="23:30"),
           restaurant("r_ny", tz="America/New_York", opens="00:00", closes="23:30")])
    ada = login()
    for rid, d, hhmm in (("r_b", "0001-01-01", "00:30"), ("r_ny", "9999-12-31", "22:00"),
                         ("r_b", "9999-12-31", "22:00"), ("r_ny", "0001-01-01", "00:00")):
        s = book(ada, rid=rid, d=d, hhmm=hhmm)
        assert s[0] in (201, 422) and (s[0] == 201 or s[1]["error"]["code"] == "validation_failed"), s
        a = call("GET", "/availability?restaurant_id=%s&date=%s&party_size=2" % (rid, d))
        assert a[0] in (200, 422), a
    ok = book(ada, rid="r_b", hhmm="19:00")[1]
    err(call("PATCH", "/reservations/" + ok["reference"], {"starts_at_local": "0001-01-01T00:30"}, ada),
        422, "validation_failed")
    # D2: HEAD / OPTIONS / unknown methods give JSON, never 5xx
    import http.client
    from urllib.parse import urlsplit
    u = urlsplit(BASE)
    for m in ("HEAD", "OPTIONS", "TRACE", "FOO"):
        c = http.client.HTTPConnection(u.hostname, u.port, timeout=5)
        c.request(m, "/health")
        r = c.getresponse()
        body = r.read()
        assert r.status < 500, (m, r.status)
        if m == "HEAD":
            assert r.status == 200 and body == b"", (m, body)
        else:
            assert json.loads(body)["error"]["code"], (m, body)
        c.close()
    # D3: non-integer party_size rejected even when numerically equal
    r4 = book(ada, rid="r_b", table="t_2", hhmm="21:00", party=4)[1]
    err(call("PATCH", "/reservations/" + r4["reference"], {"party_size": 4.0}, ada), 422, "validation_failed")
    err(call("POST", "/reservation-moves", {"moves": [{"reference": r4["reference"], "party_size": 4.0}]}, ada, k()),
        422, "validation_failed")
    assert call("GET", "/reservations/" + r4["reference"], token=ada)[1] == r4


@test
def combined_tables():
    r = restaurant()
    r["combinable"] = [["t_1", "t_2"], ["t_2", "t_3"]]
    reset([r])
    ada, bob = login(), login("bob@example.com")
    d = day()
    av = call("GET", "/availability?restaurant_id=r_anker&date=%s&party_size=6" % d)[1]["slots"][2]
    assert av["available_table_ids"] == ["t_3"], av
    assert av["available_options"] == [{"table_ids": ["t_3"], "capacity": 6},
                                       {"table_ids": ["t_1", "t_2"], "capacity": 6},
                                       {"table_ids": ["t_2", "t_3"], "capacity": 10}], av
    assert call("GET", "/restaurants/r_anker")[1]["combinable"] == r["combinable"]
    pb = lambda tok, ids, party=6, hhmm="19:00", extra=None: call("POST", "/reservations", dict(
        {"restaurant_id": "r_anker", "table_ids": ids, "starts_at_local": d + "T" + hhmm, "party_size": party},
        **(extra or {})), tok, k())
    s = pb(ada, ["t_2", "t_1"])
    assert s[0] == 201 and s[1]["table_ids"] == ["t_1", "t_2"] and "table_id" not in s[1], s
    single = book(bob, table="t_3", hhmm="19:00")[1]
    assert single["table_ids"] == ["t_3"] and single["table_id"] == "t_3"
    err(pb(bob, ["t_1", "t_3"], hhmm="21:00"), 422, "combination_not_allowed")
    err(pb(bob, ["t_1", "t_2", "t_3"], hhmm="21:00"), 422, "combination_not_allowed")
    err(pb(bob, ["t_1", "t_1"], hhmm="21:00"), 422, "validation_failed")
    err(pb(bob, [], hhmm="21:00"), 422, "validation_failed")
    err(pb(bob, ["t_1", "t_9"], hhmm="21:00"), 404, "not_found")
    err(pb(bob, ["t_1", "t_2"], party=7, hhmm="21:00"), 422, "party_exceeds_capacity")
    err(pb(bob, ["t_1", "t_2"], hhmm="21:00", extra={"table_id": "t_1"}), 422, "validation_failed")
    err(pb(bob, ["t_2", "t_3"], hhmm="20:00"), 409, "table_unavailable")
    err(book(bob, table="t_1", hhmm="19:30", party=2), 409, "table_unavailable")
    av = call("GET", "/availability?restaurant_id=r_anker&date=%s&party_size=1" % d)[1]["slots"][2]
    assert av["available_table_ids"] == [] and av["available_options"] == []
    # PATCH combined -> single, and cancel frees all
    p = call("PATCH", "/reservations/" + s[1]["reference"], {"table_ids": ["t_2"], "party_size": 4}, ada)
    assert p[0] == 200 and p[1]["table_id"] == "t_2", p
    assert book(bob, table="t_1", hhmm="19:00", party=2)[0] == 201
    p = call("PATCH", "/reservations/" + s[1]["reference"], {"table_ids": ["t_2", "t_3"], "party_size": 8,
                                                             "starts_at_local": d + "T21:00"}, ada)
    assert p[0] == 200 and p[1]["table_ids"] == ["t_2", "t_3"], p
    call("POST", "/reservations/%s/cancel" % s[1]["reference"], token=ada)
    av = call("GET", "/availability?restaurant_id=r_anker&date=%s&party_size=1" % d)[1]["slots"][6]
    assert av["available_table_ids"] == ["t_1", "t_2", "t_3"], av
    # moves with table_ids: swap a pair booking and a single
    a = pb(ada, ["t_1", "t_2"], hhmm="21:30")[1]
    b = book(ada, table="t_3", hhmm="21:30", party=2)[1]
    mv = call("POST", "/reservation-moves", {"moves": [
        {"reference": a["reference"], "table_ids": ["t_2", "t_3"]},
        {"reference": b["reference"], "table_id": "t_1"}]}, ada, k())
    assert mv[0] == 201 and [x["table_ids"] for x in mv[1]["reservations"]] == [["t_2", "t_3"], ["t_1"]], mv
    err(call("POST", "/reservation-moves", {"moves": [
        {"reference": b["reference"], "table_ids": ["t_2"]}]}, ada, k()), 409, "table_unavailable")
    # concurrent pair vs single on a member
    reset([r])
    ada, bob = login(), login("bob@example.com")
    for _ in range(3):
        out = []
        hh = ["18:00", "19:30", "21:00"][_]
        ths = [threading.Thread(target=lambda: out.append(pb(ada, ["t_1", "t_2"], hhmm=hh))),
               threading.Thread(target=lambda: out.append(book(bob, table="t_2", hhmm=hh, party=2)))]
        [t.start() for t in ths]
        [t.join() for t in ths]
        assert sorted(x[0] for x in out) == [201, 409], out


@test
def stage1_export_import():
    reset()
    ada = login()
    ex = call("GET", "/_test/export")[1]
    st = ex["state"]
    for rec in st["reservations"].values():
        pass
    # simulate a stage-1 export: drop combinable, table_ids -> table_id
    first = book(ada, hhmm="19:00")
    ex = call("GET", "/_test/export")[1]
    for rest in ex["state"]["restaurants"].values():
        rest.pop("combinable", None)
    for rec in ex["state"]["reservations"].values():
        rec["table_id"] = rec.pop("table_ids")[0]
    reset()
    assert call("POST", "/_test/import", ex)[0] == 204
    got = call("GET", "/reservations/" + first[1]["reference"], token=ada)
    assert got[0] == 200 and got[1]["table_id"] == "t_2", got
    err(book(ada, hhmm="19:00"), 409, "table_unavailable")


if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
            print("PASS", t.__name__)
        except Exception as e:
            failed += 1
            print("FAIL", t.__name__, repr(e)[:600])
    print("%d passed, %d failed" % (len(TESTS) - failed, failed))
    sys.exit(1 if failed else 0)
