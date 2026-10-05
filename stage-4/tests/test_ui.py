"""Browser tests for the stage-2 UI (Playwright). Run against a running container:
BASE=http://localhost:8080 <python with playwright> tests/test_ui.py
"""
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from test_api import BASE, USERS, call, day, restaurant  # noqa: E402


def sel(t):
    return "[data-testid='%s']" % t


def seed(combinable=None):
    r = restaurant()
    if combinable:
        r["combinable"] = combinable
    s = call("POST", "/_test/reset", {"users": USERS, "restaurants": [r], "reservations": []})
    assert s[0] == 204, s


def login(page):
    page.goto(BASE + "/login")
    page.fill(sel("login-email"), "ada@example.com")
    page.fill(sel("login-password"), "correct horse")
    page.click(sel("login-submit"))
    page.wait_for_selector(sel("current-user"))


def search(page, party, nav=True):
    if nav:
        page.goto(BASE + "/")
    page.select_option(sel("restaurant-select"), "r_anker")
    page.fill(sel("date-input"), day())
    page.fill(sel("party-size-input"), str(party))
    page.click(sel("search-button"))


TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


@test
def out_of_order_search(page):
    seed()
    held = []

    def handler(route):
        if "party_size=6" in route.request.url:
            held.append(route)  # answer A later
        else:
            route.continue_()
    page.route("**/availability?*", handler)
    page.goto(BASE + "/")
    search(page, 6, nav=False)
    for _ in range(50):
        if held:
            break
        page.wait_for_timeout(50)
    search(page, 2, nav=False)
    page.wait_for_selector(sel("availability-grid"))
    assert page.get_attribute(sel("slot-t_1-19:00"), "data-available") == "true"
    held[0].continue_()
    page.wait_for_timeout(800)
    assert page.get_attribute(sel("slot-t_1-19:00"), "data-available") == "true", "late response A restored"
    page.unroute("**/availability?*")


def lose_first_post(page, keys):
    """Let the first booking reach the server, then drop its response."""
    state = {"n": 0}

    def handler(route):
        req = route.request
        if req.method != "POST":
            return route.continue_()
        keys.append((req.headers.get("idempotency-key"), req.post_data))
        state["n"] += 1
        if state["n"] == 1:
            route.fetch()  # the booking commits on the server
            return route.abort("connectionreset")
        route.continue_()
    page.route("**/reservations", handler)


@test
def lost_response_then_retry(page):
    seed()
    login(page)
    search(page, 4)
    page.click(sel("slot-t_2-19:00"))
    keys = []
    lose_first_post(page, keys)
    page.click(sel("booking-submit"))
    page.wait_for_selector(sel("booking-uncertain"))
    assert page.text_content(sel("booking-uncertain")).strip()
    assert page.query_selector(sel("booking-error")) is None
    assert page.query_selector(sel("confirmation")) is None
    page.click(sel("booking-submit"))
    page.wait_for_selector(sel("confirmation"))
    assert page.query_selector(sel("booking-uncertain")) is None and page.query_selector(sel("booking-error")) is None
    assert keys[0] == keys[1], keys
    ref = page.text_content(sel("confirmation-reference"))
    ada = call("POST", "/auth/login", {"email": "ada@example.com", "password": "correct horse"})[1]["token"]
    mine = call("GET", "/reservations", token=ada)[1]["reservations"]
    assert [r["reference"] for r in mine] == [ref], (mine, ref)
    page.unroute("**/reservations")


@test
def upgrade_between_requests(page):
    seed()
    login(page)
    search(page, 4)
    page.click(sel("slot-t_2-19:00"))
    keys = []
    lose_first_post(page, keys)
    page.click(sel("booking-submit"))
    page.wait_for_selector(sel("booking-uncertain"))
    ex = call("GET", "/_test/export")[1]
    seed()
    assert call("POST", "/_test/import", ex)[0] == 204
    page.click(sel("booking-submit"))
    page.wait_for_selector(sel("confirmation"))
    assert keys[0] == keys[1]
    assert page.query_selector(sel("current-user")) is not None
    ref = page.text_content(sel("confirmation-reference"))
    page.unroute("**/reservations")
    page.click("a[href='/lookup']")
    page.fill(sel("lookup-reference-input"), ref)
    page.click(sel("lookup-submit"))
    page.wait_for_selector(sel("reservation-detail"))
    assert page.text_content(sel("reservation-status")) == "confirmed"


@test
def confirmed_rejection_after_uncertain(page):
    seed()
    login(page)
    search(page, 4)
    page.click(sel("slot-t_2-19:00"))
    page.route("**/reservations", lambda route: route.abort("connectionreset")
               if route.request.method == "POST" else route.continue_())
    page.click(sel("booking-submit"))
    page.wait_for_selector(sel("booking-uncertain"))
    page.unroute("**/reservations")
    bob = call("POST", "/auth/login", {"email": "bob@example.com", "password": "correct horse"})[1]["token"]
    assert call("POST", "/reservations", {"restaurant_id": "r_anker", "table_id": "t_2",
                                          "starts_at_local": day() + "T19:00", "party_size": 2}, bob, "x")[0] == 201
    page.click(sel("booking-submit"))
    page.wait_for_selector(sel("booking-error"))
    assert page.query_selector(sel("booking-uncertain")) is None
    assert page.query_selector(sel("confirmation")) is None
    assert page.input_value(sel("booking-party-size")) == "4"
    page.wait_for_selector(sel("slot-t_2-19:00") + "[data-available='false']")


@test
def combination_flow(page):
    seed([["t_1", "t_2"], ["t_2", "t_3"]])
    login(page)
    search(page, 6)
    page.wait_for_selector(sel("availability-grid"))
    assert page.query_selector(sel("slot-t_1+t_3-19:00")) is None
    page.click(sel("slot-t_1+t_2-19:00"))
    summary = page.text_content(sel("booking-summary"))
    assert "1" in summary and "2" in summary and "19:00" in summary, summary
    page.click(sel("booking-submit"))
    page.wait_for_selector(sel("confirmation"))
    tables = page.text_content(sel("confirmation-tables"))
    assert "1" in tables and "2" in tables, tables
    ref = page.text_content(sel("confirmation-reference"))
    page.wait_for_selector(sel("slot-t_1-19:00") + "[data-available='false']")
    page.goto(BASE + "/lookup")
    page.fill(sel("lookup-reference-input"), ref)
    page.click(sel("lookup-submit"))
    page.wait_for_selector(sel("reservation-tables"))
    assert "1" in page.text_content(sel("reservation-tables"))


@test
def mobile_no_horizontal_scroll(page):
    seed([["t_1", "t_2"]])
    page.set_viewport_size({"width": 375, "height": 800})
    login(page)
    search(page, 2)
    page.wait_for_selector(sel("availability-grid"))
    page.click(sel("slot-t_2-19:00"))
    page.wait_for_selector(sel("booking-form"))
    for path in (None, "/lookup", "/signup"):
        if path:
            page.goto(BASE + path)
        w = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        assert w[0] <= w[1], (path, w)
    page.set_viewport_size({"width": 1280, "height": 800})


@test
def policy_seat_labels(page):
    r = restaurant()
    r["manager_user_ids"] = ["u_ada"]
    r["combinable"] = [["t_1", "t_2"]]
    assert call("POST", "/_test/reset", {"users": USERS, "restaurants": [r], "reservations": []})[0] == 204
    ada = call("POST", "/auth/login", {"email": "ada@example.com", "password": "correct horse"})[1]["token"]
    pol = {"effective_from": day(), "slot_minutes": 30, "reservation_duration_minutes": 90,
           "cancellation_cutoff_minutes": 120,
           "opening_hours": [{"weekday": w, "opens": "18:00", "closes": "23:00"}
                             for w in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")],
           "capacities": {"t_1": 6, "t_2": 1, "t_3": 6}}
    assert call("POST", "/restaurants/r_anker/policies", pol, ada, "pol-ui")[0] == 201
    search(page, 3)
    page.wait_for_selector(sel("availability-grid"))
    assert "6 seats" in page.text_content(sel("slot-t_1-19:00"))
    assert page.get_attribute(sel("slot-t_1-19:00"), "data-available") == "true"
    t2 = page.text_content(sel("slot-t_2-19:00"))
    assert "1 seat" in t2 and "too small" in t2, t2
    assert "7 seats" in page.text_content(sel("slot-t_1+t_2-19:00"))


if __name__ == "__main__":
    failed = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for t in TESTS:
            ctx = browser.new_context()
            page = ctx.new_page()
            page.set_default_timeout(8000)
            try:
                t(page)
                print("PASS", t.__name__)
            except Exception as e:
                failed += 1
                print("FAIL", t.__name__, repr(e)[:500])
            ctx.close()
        browser.close()
    print("%d passed, %d failed" % (len(TESTS) - failed, failed))
    sys.exit(1 if failed else 0)
