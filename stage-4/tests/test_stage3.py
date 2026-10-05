"""Stage-3 black-box tests. Run: BASE=http://localhost:8080 python3 tests/test_stage3.py"""
import datetime as dt
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(__file__))
from test_api import USERS, call, day, err, k, login, restaurant, book  # noqa: E402

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def seed(combinable=None, reservations=None, **kw):
    r = restaurant(**kw)
    r["manager_user_ids"] = ["u_ada"]
    if combinable:
        r["combinable"] = combinable
    s = call("POST", "/_test/reset", {"users": USERS, "restaurants": [r], "reservations": reservations or []})
    assert s[0] == 204, s


def policy(date, **over):
    p = {"effective_from": date, "slot_minutes": 30, "reservation_duration_minutes": 90,
         "cancellation_cutoff_minutes": 120,
         "opening_hours": [{"weekday": w, "opens": "18:00", "closes": "23:00"}
                           for w in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")],
         "capacities": {"t_1": 2, "t_2": 4, "t_3": 6}}
    p.update(over)
    return p


def publish(tok, body, key=None):
    return call("POST", "/restaurants/r_anker/policies", body, tok, key or k())


def hist(tok, ref):
    s = call("GET", "/reservations/%s/history" % ref, token=tok)
    assert s[0] == 200, s
    return s[1]["entries"]


def avail(d, party, extra=""):
    return call("GET", "/availability?restaurant_id=r_anker&date=%s&party_size=%s%s" % (d, party, extra))


@test
def explain():
    seed()
    ada = login()
    book(ada, table="t_2", hhmm="19:00", party=2)
    d = day()
    plain = avail(d, 4)[1]
    assert all("explain" not in s for s in plain["slots"])
    for v in ("false", "1", "", "TRUE"):
        err(avail(d, 4, "&explain=" + v), 422, "validation_failed")
    body = avail(d, 4, "&explain=true")[1]
    s19 = [s for s in body["slots"] if s["starts_at_local"].endswith("19:00")][0]
    assert [e["table_id"] for e in s19["explain"]] == ["t_1", "t_2", "t_3"]
    t1, t2, t3 = s19["explain"]
    assert t1["rules"] == [{"rule": "capacity", "holds": False}, {"rule": "no_overlap", "holds": True}]
    assert t2["rules"] == [{"rule": "capacity", "holds": True}, {"rule": "no_overlap", "holds": False}]
    assert t3["available"] and t3["policy_version"] == 0
    for s in body["slots"]:
        assert [e["table_id"] for e in s["explain"] if e["available"]] == s["available_table_ids"]
    # both false: party 3 on t_1 which is not booked -> capacity false; book t_1 then both false
    book(ada, table="t_1", hhmm="19:00", party=2)
    s19 = [s for s in avail(d, 3, "&explain=true")[1]["slots"] if s["starts_at_local"].endswith("19:00")][0]
    assert s19["explain"][0]["rules"] == [{"rule": "capacity", "holds": False}, {"rule": "no_overlap", "holds": False}]


@test
def history_rules():
    seed([["t_1", "t_2"]])
    ada, bob = login(), login("bob@example.com")
    body = {"restaurant_id": "r_anker", "table_id": "t_2", "starts_at_local": day() + "T19:00", "party_size": 4}
    r = call("POST", "/reservations", body, ada, "h1")[1]
    assert r["revision"] == 1 and r["accepted_terms"]["policy_version"] == 0
    assert call("POST", "/reservations", body, ada, "h1")[0] == 200  # replay records nothing
    e = hist(ada, r["reference"])
    assert len(e) == 1 and e[0]["seq"] == 1 and e[0]["event"] == "created" and e[0]["revision"] == 1
    assert e[0]["changes"] == [{"field": "table_id", "from": None, "to": "t_2"},
                               {"field": "starts_at_local", "from": None, "to": day() + "T19:00"},
                               {"field": "party_size", "from": None, "to": 4}]
    p = call("PATCH", "/reservations/" + r["reference"], {"table_id": "t_2", "party_size": 4}, ada)
    assert p[0] == 200 and p[1]["revision"] == 1
    assert len(hist(ada, r["reference"])) == 1
    p = call("PATCH", "/reservations/" + r["reference"], {"party_size": 3, "starts_at_local": day() + "T20:00",
                                                          "table_id": "t_3"}, ada)[1]
    assert p["revision"] == 2
    e = hist(ada, r["reference"])
    assert e[1]["event"] == "changed" and e[1]["revision"] == 2 and [c["field"] for c in e[1]["changes"]] == \
        ["table_id", "starts_at_local", "party_size"], e
    p = call("PATCH", "/reservations/" + r["reference"], {"table_ids": ["t_2", "t_1"], "party_size": 5}, ada)[1]
    e = hist(ada, r["reference"])
    assert e[2]["changes"][0] == {"field": "table_ids", "from": ["t_3"], "to": ["t_1", "t_2"]}, e[2]
    # reversed pair alone is a no-op
    call("PATCH", "/reservations/" + r["reference"], {"table_ids": ["t_2", "t_1"]}, ada)
    assert len(hist(ada, r["reference"])) == 3
    c = call("POST", "/reservations/%s/cancel" % r["reference"], token=ada)[1]
    assert c["revision"] == 4
    assert call("POST", "/reservations/%s/cancel" % r["reference"], token=ada)[1]["revision"] == 4
    e = hist(ada, r["reference"])
    assert [x["seq"] for x in e] == [1, 2, 3, 4] and e[-1]["event"] == "cancelled" and e[-1]["changes"] == []
    err(call("PATCH", "/reservations/" + r["reference"], {"party_size": 2}, ada), 409, "reservation_cancelled")
    assert len(hist(ada, r["reference"])) == 4
    dec = call("GET", "/reservations/%s/decision" % r["reference"], token=ada)[1]
    assert dec == {"reference": r["reference"], "revision": 4, "accepted_terms": c["accepted_terms"]}
    for tok in (None, bob):
        err(call("GET", "/reservations/%s/history" % r["reference"], token=tok), 404, "not_found")
        err(call("GET", "/reservations/%s/decision" % r["reference"], token=tok), 404, "not_found")
    pair = call("POST", "/reservations", {"restaurant_id": "r_anker", "table_ids": ["t_2", "t_1"],
                                          "starts_at_local": day() + "T21:00", "party_size": 5}, ada, k())[1]
    assert hist(ada, pair["reference"])[0]["changes"][0] == {"field": "table_ids", "from": None, "to": ["t_1", "t_2"]}


@test
def policies():
    seed()
    ada, bob = login(), login("bob@example.com")
    d = day()
    err(call("POST", "/restaurants/r_anker/policies", policy(d), None, k()), 401, "unauthenticated")
    err(call("POST", "/restaurants/r_anker/policies", policy(d), ada), 400, "missing_idempotency_key")
    err(call("POST", "/restaurants/nope/policies", policy(d), ada, k()), 404, "not_found")
    err(publish(bob, policy(d)), 403, "forbidden")
    bads = [policy("2026-02-30"), policy(d, slot_minutes=0), policy(d, slot_minutes=True),
            policy(d, reservation_duration_minutes=1441), policy(d, cancellation_cutoff_minutes=-1),
            policy(d, cancellation_cutoff_minutes=10081), policy(d, capacities={"t_1": 2, "t_2": 4}),
            policy(d, capacities={"t_1": 2, "t_2": 4, "t_3": 101}),
            policy(d, capacities={"t_1": 2, "t_2": 4, "t_3": 6, "t_9": 1}),
            policy(d, opening_hours=[{"weekday": "mon", "opens": "18:00", "closes": "23:00"}] * 2),
            policy(d, opening_hours=[{"weekday": "xyz", "opens": "18:00", "closes": "23:00"}]),
            policy(d, opening_hours=[{"weekday": "mon", "opens": "23:00", "closes": "18:00"}]),
            {k_: v for k_, v in policy(d).items() if k_ != "capacities"}]
    for b in bads:
        err(publish(ada, b), 422, "validation_failed")
    assert call("GET", "/restaurants/r_anker/policies")[1] == {"policies": []}
    p1 = publish(ada, dict(policy(d, reservation_duration_minutes=60), extra=1), "pk")
    assert p1[0] == 201 and p1[1]["policy_version"] == 1 and "extra" not in p1[1], p1
    assert publish(ada, dict(policy(d, reservation_duration_minutes=60), extra=1), "pk") == (200, p1[1])
    # earlier effective date published later -> version 2, does not override date d
    p2 = publish(ada, policy(day(-30), reservation_duration_minutes=120))[1]
    assert p2["policy_version"] == 2
    b = book(ada, hhmm="19:00", party=2)[1]
    assert b["accepted_terms"]["policy_version"] == 1 and b["ends_at"][11:16] == "20:00", b
    assert "effective_from" not in b["accepted_terms"]
    b2 = book(ada, d=day(-1), hhmm="19:00", party=2)[1]
    assert b2["accepted_terms"]["policy_version"] == 2
    # same date supersedes for future decisions; existing booking unchanged
    p3 = publish(ada, policy(d, reservation_duration_minutes=30, capacities={"t_1": 2, "t_2": 1, "t_3": 6}))[1]
    assert p3["policy_version"] == 3
    assert call("GET", "/reservations/" + b["reference"], token=ada)[1] == b
    assert [p["policy_version"] for p in call("GET", "/restaurants/r_anker/policies")[1]["policies"]] == [1, 2, 3]
    assert call("GET", "/restaurants/r_anker")[1]["reservation_duration_minutes"] == 90
    a = avail(d, 2, "&explain=true")[1]["slots"][0]
    assert a["explain"][0]["policy_version"] == 3 and a["available_table_ids"] == ["t_1", "t_3"], a
    err(book(ada, table="t_2", hhmm="21:00", party=2), 422, "party_exceeds_capacity")
    # real amendment adopts new terms; old entries keep old terms
    p = call("PATCH", "/reservations/" + b["reference"], {"starts_at_local": d + "T21:00", "table_id": "t_3"}, ada)[1]
    assert p["revision"] == 2 and p["accepted_terms"]["policy_version"] == 3 and p["ends_at"][11:16] == "21:30"
    e = hist(ada, b["reference"])
    assert e[0]["accepted_terms"]["policy_version"] == 1 and e[1]["accepted_terms"]["policy_version"] == 3
    # manager cannot read other's history
    bb = book(bob, table="t_3", hhmm="18:00", party=2)[1]
    err(call("GET", "/reservations/%s/history" % bb["reference"], token=ada), 404, "not_found")


@test
def expected_revision():
    seed()
    ada = login()
    r = book(ada, hhmm="19:00", party=2)[1]
    for v in (0, -1, "1", True, 1.5):
        err(call("PATCH", "/reservations/" + r["reference"], {"party_size": 3, "expected_revision": v}, ada),
            422, "validation_failed")
    err(call("PATCH", "/reservations/" + r["reference"], {"party_size": 3, "expected_revision": 2}, ada),
        409, "stale_revision")
    past = book(ada, d=day(-1), hhmm="19:00")[1]
    err(call("PATCH", "/reservations/" + past["reference"], {"party_size": 1, "expected_revision": 5}, ada),
        409, "stale_revision")
    out = []
    ths = [threading.Thread(target=lambda p=p: out.append(call(
        "PATCH", "/reservations/" + r["reference"], {"party_size": p, "expected_revision": 1}, ada)))
        for p in (3, 4, 3, 4, 3, 4)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    codes = sorted(x[0] for x in out)
    assert codes.count(200) == 1 and codes.count(409) == 5, out
    assert call("GET", "/reservations/" + r["reference"], token=ada)[1]["revision"] == 2


@test
def series():
    seed()
    ada, bob = login(), login("bob@example.com")
    anchor = book(ada, hhmm="19:00", party=2)[1]
    body = {"anchor_reference": anchor["reference"], "count": 3, "interval_weeks": 2}
    err(call("POST", "/series", body), 401, "unauthenticated")
    err(call("POST", "/series", body, ada), 400, "missing_idempotency_key")
    for bad_ in ({"count": 1}, {"count": 13}, {"count": True}, {"interval_weeks": 5}, {"interval_weeks": 0},
                 {"anchor_reference": 5}):
        err(call("POST", "/series", dict(body, **bad_), ada, k()), 422, "validation_failed")
    err(call("POST", "/series", body, bob, k()), 404, "not_found")
    # occurrence 2 blocked by bob -> whole adoption fails, nothing left behind
    d2 = (dt.date.fromisoformat(day()) + dt.timedelta(days=28)).isoformat()
    blocker = book(bob, d=d2, hhmm="19:30", party=2)
    assert blocker[0] == 201
    before = len(call("GET", "/reservations", token=ada)[1]["reservations"])
    err(call("POST", "/series", body, ada, "s1"), 409, "table_unavailable")
    assert len(call("GET", "/reservations", token=ada)[1]["reservations"]) == before
    call("POST", "/reservations/%s/cancel" % blocker[1]["reference"], token=bob)
    s = call("POST", "/series", body, ada, "s1")
    assert s[0] == 201 and s[1]["revision"] == 1 and s[1]["interval_weeks"] == 2, s
    occ = s[1]["occurrences"]
    assert [o["index"] for o in occ] == [0, 1, 2] and occ[0]["reservation"] == anchor
    assert occ[2]["reservation"]["starts_at_local"] == d2 + "T19:00"
    assert len({o["reference"] for o in occ}) == 3 and not any(o["exception"] for o in occ)
    assert hist(ada, anchor["reference"]) and len(hist(ada, anchor["reference"])) == 1
    err(call("POST", "/series", body, ada, k()), 409, "already_in_series")
    sid = s[1]["series_id"]
    err(call("GET", "/series/" + sid, token=bob), 404, "not_found")
    err(call("GET", "/series/" + sid), 404, "not_found")
    err(book(bob, d=d2, hhmm="19:00", party=2), 409, "table_unavailable")
    # no-op patch: nothing; real patch: exception + series revision
    call("PATCH", "/reservations/" + occ[1]["reference"], {"party_size": 2}, ada)
    g = call("GET", "/series/" + sid, token=ada)[1]
    assert g["revision"] == 1 and not g["occurrences"][1]["exception"]
    call("PATCH", "/reservations/" + occ[1]["reference"], {"party_size": 1}, ada)
    g = call("GET", "/series/" + sid, token=ada)[1]
    assert g["revision"] == 2 and g["occurrences"][1]["exception"]
    call("POST", "/reservations/%s/cancel" % anchor["reference"], token=ada)
    call("POST", "/reservations/%s/cancel" % anchor["reference"], token=ada)
    g = call("GET", "/series/" + sid, token=ada)[1]
    assert g["revision"] == 3 and not g["occurrences"][0]["exception"]
    assert g["occurrences"][0]["reservation"]["status"] == "cancelled"
    assert g["occurrences"][2]["reservation"]["status"] == "confirmed"
    assert call("POST", "/series", body, ada, "s1") == (200, s[1])
    err(call("POST", "/series", body, ada, k()), 409, "reservation_cancelled")
    # cancelled anchor before already_in_series; cutoff on anchor
    past = book(ada, d=day(-1), hhmm="19:00")[1]
    err(call("POST", "/series", dict(body, anchor_reference=past["reference"]), ada, k()), 409, "cutoff_passed")


@test
def series_dst_and_policy():
    seed(opens="00:00", closes="23:30")
    ada = login()
    # anchor on 2026-03-15 02:30 Berlin (past, so cutoff blocks) -> use a far future spring date instead
    anchor = book(ada, d="2027-03-14", hhmm="02:30", party=2)[1]
    err(call("POST", "/series", {"anchor_reference": anchor["reference"], "count": 3, "interval_weeks": 1},
             ada, k()), 422, "invalid_local_time")
    assert call("GET", "/reservations/%s" % anchor["reference"], token=ada)[1]["revision"] == 1
    p = publish(ada, policy("2027-03-20", reservation_duration_minutes=60,
                            opening_hours=[{"weekday": w, "opens": "00:00", "closes": "23:30"}
                                           for w in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")]))[1]
    a2 = book(ada, d="2027-03-14", hhmm="12:00", party=2)[1]
    s = call("POST", "/series", {"anchor_reference": a2["reference"], "count": 2, "interval_weeks": 1}, ada, k())
    assert s[0] == 201, s
    o1 = s[1]["occurrences"][1]["reservation"]
    assert o1["accepted_terms"]["policy_version"] == p["policy_version"] and o1["ends_at"][11:16] == "13:00", o1


@test
def moves_under_policies():
    seed()
    ada = login()
    a = book(ada, table="t_2", hhmm="19:00", party=2)[1]
    b = book(ada, table="t_3", hhmm="19:00", party=2)[1]
    s = call("POST", "/series", {"anchor_reference": b["reference"], "count": 2, "interval_weeks": 1}, ada, k())[1]
    body = {"moves": [{"reference": a["reference"], "table_id": "t_3"},
                      {"reference": b["reference"], "table_id": "t_2"},
                      {"reference": s["occurrences"][1]["reference"]}]}
    err(call("POST", "/reservation-moves", dict(body, moves=[dict(body["moves"][0], expected_revision=3)]),
             ada, k()), 409, "stale_revision")
    err(call("POST", "/reservation-moves", dict(body, moves=[dict(body["moves"][0], expected_revision="1")]),
             ada, k()), 422, "validation_failed")
    m = call("POST", "/reservation-moves", body, ada, "mv")
    assert m[0] == 201, m
    rs = m[1]["reservations"]
    assert [r["revision"] for r in rs] == [2, 2, 1]
    assert len(hist(ada, a["reference"])) == 2 and len(hist(ada, s["occurrences"][1]["reference"])) == 1
    g = call("GET", "/series/" + s["series_id"], token=ada)[1]
    assert g["revision"] == 2 and g["occurrences"][0]["exception"] and not g["occurrences"][1]["exception"]
    assert call("POST", "/reservation-moves", body, ada, "mv") == (200, m[1])
    assert call("GET", "/series/" + s["series_id"], token=ada)[1]["revision"] == 2
    # failed batch changes nothing
    c = book(ada, table="t_1", hhmm="21:00", party=2)[1]
    bad_ = {"moves": [{"reference": a["reference"], "starts_at_local": day() + "T21:00", "table_id": "t_1"}]}
    err(call("POST", "/reservation-moves", bad_, ada, k()), 409, "table_unavailable")
    assert call("GET", "/reservations/" + a["reference"], token=ada)[1]["revision"] == 2
    assert len(hist(ada, a["reference"])) == 2 and c


@test
def upgrade_from_stage2_export():
    seed()
    ada = login()
    r = call("POST", "/reservations", {"restaurant_id": "r_anker", "table_id": "t_2",
                                       "starts_at_local": day() + "T19:00", "party_size": 2}, ada, "up")
    ex = call("GET", "/_test/export")[1]
    st = ex["state"]
    st.pop("meta")
    st.pop("series")
    for rest in st["restaurants"].values():
        rest.pop("manager_user_ids")
    for rec in st["reservations"].values():
        for f in ("terms", "revision", "history", "series_id"):
            rec.pop(f)
    seed()
    assert call("POST", "/_test/import", ex)[0] == 204
    got = call("GET", "/reservations/" + r[1]["reference"], token=ada)[1]
    assert got["revision"] == 1 and got["accepted_terms"]["policy_version"] == 0
    assert hist(ada, r[1]["reference"])[0]["event"] == "created"
    assert call("POST", "/reservations", {"restaurant_id": "r_anker", "table_id": "t_2",
                                          "starts_at_local": day() + "T19:00", "party_size": 2}, ada, "up") == (200, r[1])
    s = call("POST", "/series", {"anchor_reference": r[1]["reference"], "count": 2, "interval_weeks": 1}, ada, k())
    assert s[0] == 201, s
    ex = call("GET", "/_test/export")[1]
    seed()
    assert call("POST", "/_test/import", ex)[0] == 204
    assert call("GET", "/series/" + s[1]["series_id"], token=ada)[1]["occurrences"][1]["reference"] == \
        s[1]["occurrences"][1]["reference"]


if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
            print("PASS", t.__name__)
        except Exception as e:
            failed += 1
            import traceback
            print("FAIL", t.__name__, repr(e)[:600], traceback.format_exc().splitlines()[-3])
    print("%d passed, %d failed" % (len(TESTS) - failed, failed))
    sys.exit(1 if failed else 0)
