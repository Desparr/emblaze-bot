"""Unit tests for RealPlannerAdapter's HTTP wiring (docs/decisions/0005-real-planner-adapter-http-client.md).

These tests mock the HTTP layer entirely (a fake `requests.Session`-shaped
object) -- there is no live emblaze backend to test against. Each test checks
that a given PlannerAdapter method calls the right HTTP method + path with the
right request body, and reshapes the (assumed) response into the exact shape
MockPlannerAdapter returns for the same method, since the rest of this bot
(blocks.py, commands.py, interactions.py) is written against that shape and
must not need to change based on which adapter is wired in.

Per the big caveat at the top of RealPlannerAdapter itself: the endpoint paths
and request/response shapes asserted here are this bot's best-effort guess,
not a verified contract -- if you get real emblaze repo access, fix both the
adapter and these tests together.
"""

import unittest

from slack_bot.planner_adapter import RealPlannerAdapter, TransitionNotAllowed


class _FakeResponse:
    def __init__(self, status_code=200, json_body=None):
        self.status_code = status_code
        self._json_body = json_body if json_body is not None else {}

    def json(self):
        return self._json_body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeSession:
    """Records every call and returns canned responses in call order (or a
    dict keyed by (method, path) if `responses_by_path` is used instead)."""

    def __init__(self, responses=None, responses_by_path=None):
        self.calls = []
        self._responses = list(responses or [])
        self._responses_by_path = responses_by_path or {}

    def request(self, method, url, *, json=None, params=None, timeout=None):
        self.calls.append({"method": method, "url": url, "json": json, "params": params})
        if (method, url) in self._responses_by_path:
            return self._responses_by_path[(method, url)]
        if self._responses:
            return self._responses.pop(0)
        return _FakeResponse(200, {})


BASE_URL = "https://emblaze.emtech.us"


def _adapter(session):
    return RealPlannerAdapter(BASE_URL, session=session)


class GetUsersTests(unittest.TestCase):
    def test_calls_get_users_endpoint_and_returns_body_as_is(self):
        body = {"simonn@emtech.us": {"role": "admin", "modules": None, "name": "Simon N."}}
        session = _FakeSession(responses=[_FakeResponse(200, body)])
        adapter = _adapter(session)

        result = adapter.get_users()

        self.assertEqual(result, body)
        self.assertEqual(session.calls[0]["method"], "GET")
        self.assertEqual(session.calls[0]["url"], f"{BASE_URL}/api/planner/users")


class GetTierWeeklyRatesTests(unittest.TestCase):
    def test_reshapes_services_list_into_tier_to_rate_dict(self):
        body = {"services": [{"tier": 5, "weeklyRate": 6000}, {"tier": 3, "weeklyRate": 4400}]}
        session = _FakeSession(responses=[_FakeResponse(200, body)])
        adapter = _adapter(session)

        result = adapter.get_tier_weekly_rates()

        self.assertEqual(result, {5: 6000, 3: 4400})
        self.assertEqual(session.calls[0]["url"], f"{BASE_URL}/api/planner/config")


class ListProjectsTests(unittest.TestCase):
    def test_passes_status_as_a_query_param(self):
        body = [{"id": "project-1", "body": {"status": "planning"}, "ver": 1}]
        session = _FakeSession(responses=[_FakeResponse(200, body)])
        adapter = _adapter(session)

        result = adapter.list_projects(status="planning")

        self.assertEqual(result, body)
        self.assertEqual(session.calls[0]["method"], "GET")
        self.assertEqual(session.calls[0]["url"], f"{BASE_URL}/api/planner/projects")
        self.assertEqual(session.calls[0]["params"], {"status": "planning"})

    def test_no_status_filter_omits_the_query_param(self):
        session = _FakeSession(responses=[_FakeResponse(200, [])])
        adapter = _adapter(session)

        adapter.list_projects()

        self.assertIsNone(session.calls[0]["params"])


class ListClientsTests(unittest.TestCase):
    def test_calls_clients_endpoint(self):
        body = [{"id": "client-1", "body": {"name": "Amazon"}}]
        session = _FakeSession(responses=[_FakeResponse(200, body)])
        adapter = _adapter(session)

        self.assertEqual(adapter.list_clients(), body)
        self.assertEqual(session.calls[0]["url"], f"{BASE_URL}/api/planner/clients")


class GetProjectTests(unittest.TestCase):
    def test_returns_project_by_id(self):
        body = {"id": "project-1", "body": {"name": "Vulcan"}, "ver": 2}
        session = _FakeSession(responses=[_FakeResponse(200, body)])
        adapter = _adapter(session)

        self.assertEqual(adapter.get_project("project-1"), body)
        self.assertEqual(session.calls[0]["url"], f"{BASE_URL}/api/planner/projects/project-1")

    def test_404_raises_key_error(self):
        session = _FakeSession(responses=[_FakeResponse(404, {})])
        adapter = _adapter(session)

        with self.assertRaises(KeyError):
            adapter.get_project("missing")


class GetClientTests(unittest.TestCase):
    def test_404_raises_key_error(self):
        session = _FakeSession(responses=[_FakeResponse(404, {})])
        adapter = _adapter(session)

        with self.assertRaises(KeyError):
            adapter.get_client("missing")


class CreateProjectTests(unittest.TestCase):
    def test_posts_body_and_actor_email_and_returns_id_and_ver(self):
        session = _FakeSession(responses=[_FakeResponse(200, {"id": "project-9", "ver": 1})])
        adapter = _adapter(session)

        result = adapter.create_project({"name": "Test"}, "simonn@emtech.us")

        self.assertEqual(result, {"id": "project-9", "ver": 1})
        call = session.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["url"], f"{BASE_URL}/api/planner/projects")
        self.assertEqual(call["json"], {"body": {"name": "Test"}, "actorEmail": "simonn@emtech.us"})


class UpdateProjectTests(unittest.TestCase):
    def test_puts_body_ver_and_actor_email(self):
        session = _FakeSession(responses=[_FakeResponse(200, {"ver": 2})])
        adapter = _adapter(session)

        result = adapter.update_project("project-1", {"name": "Test"}, 1, "simonn@emtech.us")

        self.assertEqual(result, {"ver": 2})
        call = session.calls[0]
        self.assertEqual(call["method"], "PUT")
        self.assertEqual(call["url"], f"{BASE_URL}/api/planner/projects/project-1")
        self.assertEqual(call["json"], {"body": {"name": "Test"}, "ver": 1, "actorEmail": "simonn@emtech.us"})

    def test_409_raises_value_error_not_a_raw_http_exception(self):
        session = _FakeSession(responses=[_FakeResponse(409, {})])
        adapter = _adapter(session)

        with self.assertRaises(ValueError):
            adapter.update_project("project-1", {}, 1, "simonn@emtech.us")

    def test_404_raises_key_error(self):
        session = _FakeSession(responses=[_FakeResponse(404, {})])
        adapter = _adapter(session)

        with self.assertRaises(KeyError):
            adapter.update_project("missing", {}, 1, "simonn@emtech.us")


class AllocateQuoteNumberTests(unittest.TestCase):
    def test_posts_and_returns_int_quote_number(self):
        session = _FakeSession(responses=[_FakeResponse(200, {"quoteNumber": 1523})])
        adapter = _adapter(session)

        result = adapter.allocate_quote_number()

        self.assertEqual(result, 1523)
        self.assertIsInstance(result, int)
        call = session.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["url"], f"{BASE_URL}/api/planner/quote-number")


class CreateQuoteTests(unittest.TestCase):
    def test_posts_body_and_actor_email(self):
        session = _FakeSession(responses=[_FakeResponse(200, {"id": "quote-1", "ver": 1})])
        adapter = _adapter(session)

        result = adapter.create_quote({"name": "Test Quote"}, "alex@emtech.us")

        self.assertEqual(result, {"id": "quote-1", "ver": 1})
        call = session.calls[0]
        self.assertEqual(call["url"], f"{BASE_URL}/api/planner/quotes")
        self.assertEqual(call["json"], {"body": {"name": "Test Quote"}, "actorEmail": "alex@emtech.us"})


class GetQuoteTests(unittest.TestCase):
    def test_404_raises_key_error(self):
        session = _FakeSession(responses=[_FakeResponse(404, {})])
        adapter = _adapter(session)

        with self.assertRaises(KeyError):
            adapter.get_quote("missing")


class ListQuotesTests(unittest.TestCase):
    def test_calls_quotes_endpoint(self):
        body = [{"id": "quote-1", "body": {}, "ver": 1}]
        session = _FakeSession(responses=[_FakeResponse(200, body)])
        adapter = _adapter(session)

        self.assertEqual(adapter.list_quotes(), body)
        self.assertEqual(session.calls[0]["url"], f"{BASE_URL}/api/planner/quotes")


class TransitionQuoteTests(unittest.TestCase):
    def _quote_response(self, approval_status):
        return _FakeResponse(200, {"id": "quote-1", "body": {"approvalStatus": approval_status}, "ver": 1})

    def _users_response(self, role):
        return _FakeResponse(200, {"alex@emtech.us": {"role": role, "modules": None, "name": "Alex"}})

    def test_eligible_role_calls_the_transition_endpoint(self):
        session = _FakeSession(
            responses=[
                self._quote_response("pending_l1"),  # get_quote (own role check)
                self._users_response("approver_l1"),  # get_users (own role check)
                _FakeResponse(200, {"ver": 2}),  # the actual transition POST
            ]
        )
        adapter = _adapter(session)

        result = adapter.transition_quote("quote-1", "pending_l2", 1, "alex@emtech.us")

        self.assertEqual(result, {"ver": 2})
        transition_call = session.calls[-1]
        self.assertEqual(transition_call["method"], "POST")
        self.assertEqual(transition_call["url"], f"{BASE_URL}/api/planner/quotes/quote-1/transition")
        self.assertEqual(
            transition_call["json"],
            {"toStatus": "pending_l2", "ver": 1, "actorEmail": "alex@emtech.us", "note": None},
        )

    def test_ineligible_role_raises_before_calling_the_transition_endpoint(self):
        # Defense in depth (guardrail 3.7): a member can't approve pending_l1 ->
        # pending_l2 -- the adapter must refuse locally without ever POSTing.
        session = _FakeSession(
            responses=[
                self._quote_response("pending_l1"),
                self._users_response("member"),
            ]
        )
        adapter = _adapter(session)

        with self.assertRaises(TransitionNotAllowed):
            adapter.transition_quote("quote-1", "pending_l2", 1, "alex@emtech.us")

        # Only the two read calls happened -- no POST to /transition.
        self.assertEqual(len(session.calls), 2)

    def test_409_raises_value_error(self):
        session = _FakeSession(
            responses=[
                self._quote_response("pending_l1"),
                self._users_response("approver_l1"),
                _FakeResponse(409, {}),
            ]
        )
        adapter = _adapter(session)

        with self.assertRaises(ValueError):
            adapter.transition_quote("quote-1", "pending_l2", 1, "alex@emtech.us")


if __name__ == "__main__":
    unittest.main()
