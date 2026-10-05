"""Stage-4 black-box tests. Run: BASE=http://localhost:8080 python3 tests/test_stage4.py"""
import datetime as dt
import os
import sys
import threading
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(__file__))
from test_api import USERS, call, day, err, k, login, restaurant, book  # noqa: E402

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def seed(reservations=None):
    r = restaurant()
    r["manager_user_ids"] = ["u_ada"]
    r["combinable"] = [["t_1", "t_2"], ["t_2", "t_3"]]
    other = restaurant("r_two")
    other["manager_user_ids"] = ["u_ada"]
    s = call("POST", "/_test/reset", {"users": USERS, "restaurants": [r, other], "reservations": reservations or []})
    assert s[0] == 204, s


def instant(hh, d=None):
    d = dt.date.fromisoformat(d or day())
    return dt.datetime.combine(d, dt.time(hh), tzinfo=ZoneInfo("Europe/Berlin")).isoformat()


def preview(tok, table="t_2", f=18, t=23, rid="r_anker", key=None):
    return call("POST", "/restaurants/%s/replans" % rid, {"table_id": table, "from": instant(f), "to": instant(t)},
                tok, key or k())


def rev(tok):
    s = preview(tok, f=6, t=7)  # an empty window: preview never changes state
    assert s[0] == 201, s
    return s[1]["restaurant_revision"]


def hist(tok, ref):
    return call("GET", "/reservations/%s/history" % ref, token=tok)[1]["entries"]


@test
def restaurant_revision_counter():
    seed()
    ada = login()
    assert rev(ada) == 0
    r = book(ada, table="t_2", hhmm="19:00", party=2)[1]
    assert rev(ada) == 1
    err(book(ada, table="t_2", hhmm="19:00", party=2), 409, "table_unavailable")
    call("PATCH", "/reservations/" + r["reference"], {"party_size": 2}, ada)
    assert rev(ada) == 1
    call("PATCH", "/reservations/" + r["reference"], {"party_size": 3}, ada)
    assert rev(ada) == 2
    body = {"restaurant_id": "r_anker", "table_id": "t_3", "starts_at_local": day() + "T19:00", "party_size": 2}
    call("POST", "/reservations", body, ada, "rk")
    call("POST", "/reservations", body, ada, "rk")
    assert rev(ada) == 3
    call("POST", "/reservations/%s/cancel" % r["reference"], token=ada)
    call("POST", "/reservations/%s/cancel" % r["reference"], token=ada)
    assert rev(ada) == 4
    pol = {"effective_from": day(30), "slot_minutes": 30, "reservation_duration_minutes": 90,
           "cancellation_cutoff_minutes": 120,
           "opening_hours": [{"weekday": "mon", "opens": "18:00", "closes": "23:00"}],
           "capacities": {"t_1": 2, "t_2": 4, "t_3": 6}}
    assert call("POST", "/restaurants/r_anker/policies", pol, ada, k())[0] == 201
    assert rev(ada) == 5
    book(ada, rid="r_two", hhmm="19:00", party=2)
    assert rev(ada) == 5  # other restaurant


@test
def replan_auth_and_validation():
    seed()
    ada, bob = login(), login("bob@example.com")
    err(call("POST", "/restaurants/r_anker/replans", {"table_id": "t_2", "from": instant(18), "to": instant(23)}),
        401, "unauthenticated")
    err(preview(bob), 403, "forbidden")
    err(preview(ada, rid="nope"), 404, "not_found")
    err(call("POST", "/restaurants/r_anker/replans", {"table_id": "t_2", "from": instant(18), "to": instant(23)},
             ada), 400, "missing_idempotency_key")
    err(preview(ada, f=23, t=18), 422, "validation_failed")
    err(preview(ada, f=18, t=18), 422, "validation_failed")
    err(call("POST", "/restaurants/r_anker/replans", {"table_id": "t_2", "from": day() + "T18:00:00",
                                                      "to": instant(23)}, ada, k()), 422, "validation_failed")
    err(preview(ada, table="t_9"), 404, "not_found")
    p = preview(ada, key="pk")
    assert p[0] == 201 and p[1]["assignments"] == [] and p[1]["moved_count"] == 0 and p[1]["unused_seats"] == 0
    assert preview(ada, key="pk") == (200, p[1])
    err(call("POST", "/restaurants/r_anker/replans", {"table_id": "t_1", "from": instant(18), "to": instant(23)},
             ada, "pk"), 409, "idempotency_key_reuse")


@test
def replan_preview_and_apply():
    seed()
    ada, bob = login(), login("bob@example.com")
    a = book(bob, table="t_2", hhmm="19:00", party=3)[1]
    b = book(bob, table="t_3", hhmm="20:00", party=2)[1]
    c = book(bob, table="t_1", hhmm="18:00", party=1)[1]  # 18:00-19:30 overlaps the closure, on t_1
    late = book(bob, table="t_2", hhmm="21:30", party=2)[1]  # outside [18:00, 21:00)
    p = preview(ada, f=18, t=21)
    assert p[0] == 201, p
    refs = sorted([a["reference"], b["reference"], c["reference"]])
    assert [x["reference"] for x in p[1]["assignments"]] == refs
    got = {x["reference"]: (x["table_ids"], x["changed"]) for x in p[1]["assignments"]}
    # a needs >=3 seats without t_2: only t_3 (every pair contains t_2). b leaves t_3 for t_1, which is
    # free after c (18:00-19:30). c stays.
    assert got == {a["reference"]: (["t_3"], True), b["reference"]: (["t_1"], True),
                   c["reference"]: (["t_1"], False)}, got
    assert p[1]["unused_seats"] == 3 + 0 + 1
    assert p[1]["moved_count"] == sum(1 for v in got.values() if v[1])
    # preview changes nothing
    assert hist(bob, a["reference"]) == hist(bob, a["reference"])[:1]
    assert call("GET", "/reservations/" + a["reference"], token=bob)[1]["table_id"] == "t_2"
    rv = p[1]["restaurant_revision"]
    ap = call("POST", "/restaurants/r_anker/replans/%s/apply" % p[1]["plan_id"], {}, ada, "ak")
    assert ap[0] == 201 and ap[1]["restaurant_revision"] == rv + 1, ap
    assert [r["reference"] for r in ap[1]["reservations"]] == refs
    na = call("GET", "/reservations/" + a["reference"], token=bob)[1]
    assert na["table_ids"] == ["t_3"] and na["revision"] == 2 and na["starts_at"] == a["starts_at"] \
        and na["ends_at"] == a["ends_at"] and na["accepted_terms"] == a["accepted_terms"]
    h = hist(bob, a["reference"])
    assert h[-1]["event"] == "reassigned" and h[-1]["plan_id"] == p[1]["plan_id"] and \
        h[-1]["changes"] == [{"field": "table_ids", "from": ["t_2"], "to": ["t_3"]}] and h[-1]["revision"] == 2
    for x in p[1]["assignments"]:
        if not x["changed"]:
            assert len(hist(bob, x["reference"])) == 1
    assert len(hist(bob, late["reference"])) == 1
    # closure effects
    sl = call("GET", "/availability?restaurant_id=r_anker&date=%s&party_size=1&explain=true" % day())[1]["slots"]
    s1830 = [s for s in sl if s["starts_at_local"].endswith("18:30")][0]
    assert "t_2" not in s1830["available_table_ids"]
    assert all("t_2" not in o["table_ids"] for o in s1830["available_options"])
    assert s1830["explain"][1]["rules"][1] == {"rule": "no_overlap", "holds": False}
    err(book(ada, table="t_2", hhmm="19:30", party=1), 409, "table_unavailable")
    err(call("PATCH", "/reservations/" + late["reference"], {"starts_at_local": day() + "T20:00"}, bob),
        409, "table_unavailable")
    # replay, already applied, stale
    assert call("POST", "/restaurants/r_anker/replans/%s/apply" % p[1]["plan_id"], {}, ada, "ak") == (200, ap[1])
    err(call("POST", "/restaurants/r_anker/replans/%s/apply" % p[1]["plan_id"], {}, ada, k()),
        409, "plan_already_applied")
    err(call("POST", "/restaurants/r_two/replans/%s/apply" % p[1]["plan_id"], {}, ada, k()), 404, "not_found")
    err(call("POST", "/restaurants/r_anker/replans/nope/apply", {}, ada, k()), 404, "not_found")
    p2 = preview(ada, table="t_1", f=12, t=13)[1]
    book(ada, rid="r_two", hhmm="19:00", party=2)  # other restaurant does not invalidate
    book(ada, table="t_3", hhmm="21:30", party=2)
    err(call("POST", "/restaurants/r_anker/replans/%s/apply" % p2["plan_id"], {}, ada, k()), 409, "stale_plan")


@test
def replan_optimum_and_infeasible():
    seed()
    ada, bob = login(), login("bob@example.com")
    # one booking on t_2 for 1 guest: candidates t_1 (1 unused), t_3 (5 unused) -> t_1
    x = book(bob, table="t_2", hhmm="19:00", party=1)[1]
    p = preview(ada)[1]
    assert p["assignments"] == [{"reference": x["reference"], "table_ids": ["t_1"], "changed": True}], p
    assert p["moved_count"] == 1 and p["unused_seats"] == 1
    # closing t_3 with x on t_2 leaves x unchanged
    p = preview(ada, table="t_3")[1]
    assert p["assignments"][0]["changed"] is False and p["moved_count"] == 0
    # infeasible: a party of 6 on t_3 needs [t_1,t_2] when t_3 closes, but x on t_2 has nowhere else to go
    y = book(bob, table="t_3", hhmm="19:00", party=6)[1]
    before = call("GET", "/reservations/" + y["reference"], token=bob)[1]
    r0 = rev(ada)
    err(preview(ada, table="t_3"), 409, "no_feasible_plan")
    assert call("GET", "/reservations/" + y["reference"], token=bob)[1] == before and rev(ada) == r0
    # cancel x: now y moves to the pair [t_1,t_2] (rank 3 before [t_2,t_3] which contains the closed table)
    call("POST", "/reservations/%s/cancel" % x["reference"], token=bob)
    p = preview(ada, table="t_3")[1]
    assert p["assignments"] == [{"reference": y["reference"], "table_ids": ["t_1", "t_2"], "changed": True}], p


@test
def concurrent_apply():
    seed()
    ada, bob = login(), login("bob@example.com")
    book(bob, table="t_2", hhmm="19:00", party=1)
    plans = [preview(ada)[1]["plan_id"] for _ in range(4)]
    out = []
    ths = [threading.Thread(target=lambda p=p: out.append(
        call("POST", "/restaurants/r_anker/replans/%s/apply" % p, {}, ada, k()))) for p in plans]
    [t.start() for t in ths]
    [t.join() for t in ths]
    assert sorted(o[0] for o in out) == [201, 409, 409, 409], out


@test
def series_amend():
    seed()
    ada, bob = login(), login("bob@example.com")
    anchor = book(ada, table="t_2", hhmm="19:00", party=2)[1]
    s = call("POST", "/series", {"anchor_reference": anchor["reference"], "count": 4, "interval_weeks": 1},
             ada, k())[1]
    sid = s["series_id"]
    path = "/series/%s/amend" % sid
    body = {"expected_revision": 1, "from_index": 1, "local_time": "20:00"}
    err(call("POST", path, body), 401, "unauthenticated")
    err(call("POST", path, body, bob, k()), 404, "not_found")
    err(call("POST", "/series/nope/amend", body, ada, k()), 404, "not_found")
    for bad_ in ({"from_index": 4}, {"from_index": -1}, {"from_index": True}, {"local_time": "24:00"},
                 {"local_time": "8:00"}, {"local_time": "20:00:00"}, {"expected_revision": 0},
                 {"expected_revision": True}):
        err(call("POST", path, dict(body, **bad_), ada, k()), 422, "validation_failed")
    err(call("POST", path, dict(body, expected_revision=2), ada, k()), 409, "stale_revision")
    # make occurrence 3 an exception: it is skipped
    occ = s["occurrences"]
    call("PATCH", "/reservations/" + occ[3]["reference"], {"party_size": 3}, ada)
    r0 = rev(ada)
    a = call("POST", path, dict(body, expected_revision=2), ada, "am")
    assert a[0] == 201, a
    o = a[1]["occurrences"]
    assert o[0]["reservation"]["starts_at_local"].endswith("19:00")
    assert o[1]["reservation"]["starts_at_local"] == occ[1]["reservation"]["starts_at_local"][:10] + "T20:00"
    assert o[2]["reservation"]["starts_at_local"].endswith("20:00") and o[3]["reservation"]["starts_at_local"].endswith("19:00")
    assert a[1]["revision"] == 3 and not o[1]["exception"] and o[3]["exception"]
    assert o[1]["reservation"]["revision"] == 2 and hist(ada, occ[1]["reference"])[-1]["event"] == "changed"
    assert rev(ada) == r0 + 1
    # all no-op: succeeds without revisions
    n = call("POST", path, dict(body, expected_revision=3), ada, k())
    assert n[0] == 201 and n[1]["revision"] == 3 and rev(ada) == r0 + 1
    # replay after a cancel still returns the original
    call("POST", "/reservations/%s/cancel" % occ[2]["reference"], token=ada)
    assert call("POST", path, dict(body, expected_revision=2), ada, "am") == (200, a[1])
    # conflict: bob takes t_2 at 18:30 on occurrence 1's date -> amend to 18:00 fails, nothing changes
    d1 = occ[1]["reservation"]["starts_at_local"][:10]
    assert book(bob, table="t_2", d=d1, hhmm="18:30", party=2)[0] == 201
    cur = call("GET", "/series/" + sid, token=ada)[1]
    err(call("POST", path, {"expected_revision": cur["revision"], "from_index": 0, "local_time": "18:00"}, ada, "am2"),
        409, "table_unavailable")
    assert call("GET", "/series/" + sid, token=ada)[1] == cur
    # non-occupancy error first: off-grid time
    err(call("POST", path, {"expected_revision": cur["revision"], "from_index": 0, "local_time": "20:10"}, ada, k()),
        422, "not_on_slot_grid")
    # concurrent amendments from the same revision: not both real
    out = []
    ths = [threading.Thread(target=lambda t=t: out.append(call(
        "POST", path, {"expected_revision": cur["revision"], "from_index": 0, "local_time": t}, ada, k())))
        for t in ("21:00", "21:30", "21:00", "21:30")]
    [t.start() for t in ths]
    [t.join() for t in ths]
    assert sorted(x[0] for x in out).count(201) == 1, out


@test
def replan_moves_series_member():
    seed()
    ada = login()
    anchor = book(ada, table="t_2", hhmm="19:00", party=1)[1]
    s = call("POST", "/series", {"anchor_reference": anchor["reference"], "count": 2, "interval_weeks": 1},
             ada, k())[1]
    p = preview(ada)[1]
    call("POST", "/restaurants/r_anker/replans/%s/apply" % p["plan_id"], {}, ada, k())
    g = call("GET", "/series/" + s["series_id"], token=ada)[1]
    assert g["revision"] == 2 and not g["occurrences"][0]["exception"]
    assert g["occurrences"][0]["reservation"]["table_ids"] == ["t_1"]
    assert g["occurrences"][1]["reservation"]["table_ids"] == ["t_2"]


@test
def upgrade_from_stage3_export():
    seed()
    ada = login()
    anchor = book(ada, table="t_2", hhmm="19:00", party=2)[1]
    s = call("POST", "/series", {"anchor_reference": anchor["reference"], "count": 2, "interval_weeks": 1},
             ada, "sk")[1]
    ex = call("GET", "/_test/export")[1]
    st = ex["state"]
    st.pop("plans")
    for m in st["meta"].values():
        m.pop("closures")
    for ser in st["series"].values():
        for o in ser["occurrences"]:
            o.pop("scheduled_date")
    seed()
    assert call("POST", "/_test/import", ex)[0] == 204
    a = call("POST", "/series/%s/amend" % s["series_id"], {"expected_revision": 1, "from_index": 0,
                                                           "local_time": "20:00"}, ada, k())
    assert a[0] == 201 and a[1]["occurrences"][1]["reservation"]["starts_at_local"].endswith("T20:00"), a
    assert call("POST", "/series", {"anchor_reference": anchor["reference"], "count": 2, "interval_weeks": 1},
                ada, "sk") == (200, s)
    p = preview(ada, f=19, t=21)
    assert p[0] == 201
    ex = call("GET", "/_test/export")[1]
    seed()
    assert call("POST", "/_test/import", ex)[0] == 204
    assert call("POST", "/restaurants/r_anker/replans/%s/apply" % p[1]["plan_id"], {}, ada, k())[0] == 201


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
