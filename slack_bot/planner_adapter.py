"""The one seam between this bot and the real Emblaze backend.

Handbook 3.2: "Reuse, don't reimplement: slack_api.py should import and call the
same functions planner_api.py uses (or make internal calls to its endpoints) so
the math, the counter, the transitions, and the won-hook are literally the same
code." This module is where that happens.

Three implementations ship here:
  - MockPlannerAdapter: fully in-memory, seeded with fake data, so the rest of
    this bot is buildable and testable *today*, with no access to the real
    emblaze repo or AWS account.
  - RealPlannerAdapter: a real HTTP client against EMBLAZE_BASE_URL's
    /api/planner/* endpoints (see its own docstring below for the load-bearing
    caveat: it is UNVERIFIED against the actual emblaze source and must be
    checked before production use).

Role hierarchy and the transition rules below mirror handbook 2.5's server-enforced
approval chain:
    draft         -> pending_l1              (anyone)
    pending_l1    -> pending_l2 / rejected   (approver_l1+)
    pending_l2    -> final_approved/rejected (approver_l2+)
    rejected      -> draft                   (anyone)
The handbook's Part 3 only specifies Slack buttons for the pending_l1/pending_l2
hops (3.5) -- final_approved -> sent -> approved isn't described as an approver
action anywhere in Part 3, so this bot does not expose buttons for it. Confirm
against the real transition endpoint before adding any.
"""

from __future__ import annotations

import itertools
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger("slack_bot.planner_adapter")

ROLE_RANK = {"member": 0, "approver_l1": 1, "approver_l2": 2, "admin": 3}

DEFAULT_TIER_WEEKLY_RATES = {5: 6000, 4: 5200, 3: 4400, 2: 3600, 1: 2800, 6: 0}

# (from_status) -> {to_status: minimum ROLE_RANK required, or None for "anyone"}
TRANSITION_RULES = {
    "draft": {"pending_l1": None},
    "pending_l1": {"pending_l2": "approver_l1", "rejected": "approver_l1"},
    "pending_l2": {"final_approved": "approver_l2", "rejected": "approver_l2"},
    "rejected": {"draft": None},
}


class TransitionNotAllowed(Exception):
    pass


def role_meets(role: str, minimum: str | None) -> bool:
    if minimum is None:
        return True
    return ROLE_RANK.get(role, -1) >= ROLE_RANK.get(minimum, 999)


def can_act_on_transition(role: str, from_status: str, to_status: str) -> bool:
    rule = TRANSITION_RULES.get(from_status, {})
    if to_status not in rule:
        return False
    return role_meets(role, rule[to_status])


class PlannerAdapter(ABC):
    @abstractmethod
    def get_users(self) -> dict:
        """{email: {role, modules, name}} -- mirrors secret emblaze-prod/sso-users (2.4)."""

    @abstractmethod
    def get_tier_weekly_rates(self) -> dict:
        """{tier_int: weekly_rate} from config.services (2.3)."""

    @abstractmethod
    def list_projects(self, status: str | None = None) -> list:
        """[{id, body, ver}], optionally filtered by body['status']."""

    @abstractmethod
    def list_teams(self) -> list:
        """[{id, body}] where body = {name, contacts: [...]} -- internal Emtech teams/departments."""

    @abstractmethod
    def get_project(self, project_id: str) -> dict:
        """-> {id, body, ver}. Raise KeyError if missing."""

    @abstractmethod
    def get_team(self, team_id: str) -> dict:
        """-> {id, body}. Raise KeyError if missing."""

    @abstractmethod
    def create_project(self, body: dict, actor_email: str) -> dict:
        """-> {id, ver}. POST /api/planner/projects (2.5)."""

    @abstractmethod
    def update_project(self, project_id: str, body: dict, ver: int, actor_email: str) -> dict:
        """-> {ver}. PUT /api/planner/projects/<id> (2.5); may raise on 409 (stale ver)."""

    @abstractmethod
    def allocate_quote_number(self) -> int:
        """-> the next server-issued quote number. POST /api/planner/quote-number (2.5). Never invent one client-side."""

    @abstractmethod
    def create_quote(self, body: dict, actor_email: str) -> dict:
        """-> {id, ver}. POST /api/planner/quotes (2.5)."""

    @abstractmethod
    def get_quote(self, quote_id: str) -> dict:
        """-> {id, body, ver}."""

    @abstractmethod
    def list_quotes(self) -> list:
        """[{id, body, ver}] -- used by /emblaze status."""

    @abstractmethod
    def transition_quote(self, quote_id: str, to_status: str, ver: int, actor_email: str, note: str | None = None) -> dict:
        """-> {ver}. POST /api/planner/quotes/<id>/transition (2.5). Server-enforced by role; raise TransitionNotAllowed if this adapter's own role check fails first (defense in depth, 3.7)."""


class MockPlannerAdapter(PlannerAdapter):
    """In-memory stand-in so the rest of the bot is runnable and testable without
    the real emblaze backend. Not persisted -- restarting the process resets state.
    """

    def __init__(self):
        self._project_ids = itertools.count(1)
        self._quote_ids = itertools.count(1)
        self._quote_number = itertools.count(1500)

        self._users = {
            "simonn@emtech.us": {"role": "admin", "modules": None, "name": "Simon N."},
            "josh@emtech.us": {"role": "approver_l2", "modules": None, "name": "Josh"},
            "priya@emtech.us": {"role": "approver_l1", "modules": None, "name": "Priya"},
            "alex@emtech.us": {"role": "member", "modules": None, "name": "Alex"},
            "desmondp@emtech.us": {"role": "admin", "modules": None, "name": "Desmond P."},
            "mattj@emtech.us": {"role": "admin", "modules": None, "name": "Matt J."},
        }

        self._tier_weekly_rates = dict(DEFAULT_TIER_WEEKLY_RATES)

        self._teams = {
            "team-1": {"id": "team-1", "body": {"name": "Field Operations", "contacts": []}, "ver": 1},
            "team-2": {"id": "team-2", "body": {"name": "Engineering", "contacts": []}, "ver": 1},
        }

        self._projects = {}
        self._quotes = {}
        self._seed_projects()

    def _seed_projects(self):
        seed_id = f"project-seed-{next(self._project_ids)}"
        self._projects[seed_id] = {
            "id": seed_id,
            "ver": 1,
            "body": {
                "name": "Vulcan Q4 Support",
                "status": "planning",
                "location": "GEG1 - Spokane",
                "capexOpex": "OPEX",
                "startDate": "2026-10-05",
                "endDate": "2026-12-18",
                "technicians": [
                    {
                        "id": "t1",
                        "tier": 3,
                        "quantity": 2,
                        "role": "install crew",
                        "nightShift": False,
                        "scheduleUnit": "week",
                        "activeWeeks": list(range(1, 11)),
                    }
                ],
                "notes": "seed data",
            },
        }

    # -- reads --------------------------------------------------------------

    def get_users(self) -> dict:
        return self._users

    def get_tier_weekly_rates(self) -> dict:
        return self._tier_weekly_rates

    def list_projects(self, status: str | None = None) -> list:
        items = list(self._projects.values())
        if status is not None:
            items = [p for p in items if p["body"].get("status") == status]
        return items

    def list_teams(self) -> list:
        return list(self._teams.values())

    def get_project(self, project_id: str) -> dict:
        project = self._projects.get(project_id)
        if project is None:
            raise KeyError(f"no such project: {project_id}")
        return project

    def get_team(self, team_id: str) -> dict:
        team = self._teams.get(team_id)
        if team is None:
            raise KeyError(f"no such team: {team_id}")
        return team

    def list_quotes(self) -> list:
        return list(self._quotes.values())

    def get_quote(self, quote_id: str) -> dict:
        quote = self._quotes.get(quote_id)
        if quote is None:
            raise KeyError(f"no such quote: {quote_id}")
        return quote

    # -- writes ---------------------------------------------------------------

    def create_project(self, body: dict, actor_email: str) -> dict:
        project_id = f"project-{next(self._project_ids)}"
        self._projects[project_id] = {"id": project_id, "ver": 1, "body": body}
        return {"id": project_id, "ver": 1}

    def update_project(self, project_id: str, body: dict, ver: int, actor_email: str) -> dict:
        current = self._projects.get(project_id)
        if current is None:
            raise KeyError(f"no such project: {project_id}")
        if current["ver"] != ver:
            raise ValueError(f"stale ver for {project_id}: had {current['ver']}, got {ver}")
        new_ver = ver + 1
        self._projects[project_id] = {"id": project_id, "ver": new_ver, "body": body}
        return {"ver": new_ver}

    def allocate_quote_number(self) -> int:
        return next(self._quote_number)

    def create_quote(self, body: dict, actor_email: str) -> dict:
        quote_id = f"quote-{next(self._quote_ids)}"
        self._quotes[quote_id] = {"id": quote_id, "ver": 1, "body": body}
        return {"id": quote_id, "ver": 1}

    def transition_quote(self, quote_id: str, to_status: str, ver: int, actor_email: str, note: str | None = None) -> dict:
        quote = self._quotes.get(quote_id)
        if quote is None:
            raise KeyError(f"no such quote: {quote_id}")
        if quote["ver"] != ver:
            raise ValueError(f"stale ver for {quote_id}: had {quote['ver']}, got {ver}")

        role = self._users.get(actor_email, {}).get("role", "member")
        from_status = quote["body"].get("approvalStatus", "draft")
        if not can_act_on_transition(role, from_status, to_status):
            raise TransitionNotAllowed(f"{actor_email} ({role}) cannot move {from_status} -> {to_status}")

        new_ver = ver + 1
        quote["body"]["approvalStatus"] = to_status
        quote["body"]["status"] = to_status
        quote["body"].setdefault("statusLog", []).append(
            {"by": actor_email, "from": from_status, "to": to_status, "note": note}
        )
        quote["ver"] = new_ver
        return {"ver": new_ver}


class RealPlannerAdapter(PlannerAdapter):
    """A real HTTP client against the Emblaze planner backend.

    =====================================================================
    UNVERIFIED -- READ BEFORE USING IN PRODUCTION.
    This class was written with no access to the real `emblaze` repo or a
    live `/api/planner/*` API (per the task that produced it: no repo/AWS
    access was available). Every path, request shape, and response shape
    below is a best-effort guess based only on:
      (a) the endpoint names/methods named in this module's PREVIOUS
          skeleton comments (themselves marked "unverified" -- traceable
          to handbook 2.5), and
      (b) MockPlannerAdapter's return shapes above, which the rest of this
          bot (blocks.py, commands.py, interactions.py, approvals.py) is
          written against and must not need to change.
    Handbook 3.8's rule applies doubly here: "if this doc and the code
    disagree, the code wins" -- and here, *this code* is the guess. Before
    flipping PLANNER_ADAPTER=real in any environment that matters, a human
    with access to the real `emblaze` repo's `planner_api.py` MUST read
    that source and correct every path/shape below that doesn't match.
    Do not remove this notice when editing this class -- update it instead
    (e.g. to "verified against planner_api.py on <date> by <name>") once
    that check has actually happened. NOTE: the /api/planner/teams path
    below (renamed from /api/planner/clients on 2026-07-21 per the
    client->team domain rename, see docs/decisions/0006-internal-teams-not-
    external-clients.md) is itself just as unverified as every other path
    here -- it has not been checked against the real API either.
    =====================================================================

    Endpoint map assumed (verify all of these):
        GET    /api/planner/users                    -> get_users
        GET    /api/planner/config                    -> get_tier_weekly_rates
        GET    /api/planner/projects?status=<status>   -> list_projects
        GET    /api/planner/teams                      -> list_teams
        GET    /api/planner/projects/<id>               -> get_project
        GET    /api/planner/teams/<id>                  -> get_team
        POST   /api/planner/projects                    -> create_project
        PUT    /api/planner/projects/<id>               -> update_project
        POST   /api/planner/quote-number                -> allocate_quote_number
        POST   /api/planner/quotes                      -> create_quote
        GET    /api/planner/quotes/<id>                  -> get_quote
        GET    /api/planner/quotes                       -> list_quotes
        POST   /api/planner/quotes/<id>/transition        -> transition_quote

    All requests/responses are assumed to be JSON. A service credential
    (bearer token, mTLS, or an internal-network allowlist) will be needed
    for these outbound calls once this app is hosted standalone -- see
    docs/decisions/0002-no-independent-datastore.md's "Consequences" for
    why that detail was deliberately left open, and
    docs/decisions/0005-real-planner-adapter-http-client.md for this
    implementation's own record.
    """

    def __init__(self, base_url: str, *, session=None, timeout: float = 10.0):
        import requests  # local import keeps `requests` optional for pure-mock test runs

        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout
        self._requests = requests

    # -- low-level HTTP helper ------------------------------------------------

    def _request(self, method: str, path: str, *, json_body: dict | None = None, params: dict | None = None):
        url = f"{self.base_url}{path}"
        resp = self.session.request(method, url, json=json_body, params=params, timeout=self.timeout)
        return resp

    def _request_or_raise(self, method: str, path: str, *, json_body: dict | None = None, params: dict | None = None,
                           not_found_message: str | None = None):
        resp = self._request(method, path, json_body=json_body, params=params)
        if not_found_message and resp.status_code == 404:
            raise KeyError(not_found_message)
        resp.raise_for_status()
        return resp.json()

    # -- reads --------------------------------------------------------------

    def get_users(self) -> dict:
        # GET /api/planner/users -- assumed to already return {email: {role, modules, name}},
        # matching MockPlannerAdapter.get_users() exactly. Verify against the real
        # allowlist loader (secret emblaze-prod/sso-users) named in the handbook.
        return self._request_or_raise("GET", "/api/planner/users")

    def get_tier_weekly_rates(self) -> dict:
        # GET /api/planner/config -- guessed response shape:
        #   {"services": [{"tier": 5, "weeklyRate": 6000}, ...]}
        # reshaped here into {tier_int: weekly_rate} to match the mock. If the
        # real endpoint already returns that flat shape, drop the reshape below.
        data = self._request_or_raise("GET", "/api/planner/config")
        services = data.get("services", data if isinstance(data, list) else [])
        return {int(item["tier"]): item["weeklyRate"] for item in services}

    def list_projects(self, status: str | None = None) -> list:
        # GET /api/planner/projects?status=<status> -- assumed to return
        # [{id, body, ver}, ...] directly (the DynamoDB single-table shape
        # per starthere/conventions/coding-conventions.md), matching the mock.
        params = {"status": status} if status is not None else None
        return self._request_or_raise("GET", "/api/planner/projects", params=params)

    def list_teams(self) -> list:
        return self._request_or_raise("GET", "/api/planner/teams")

    def get_project(self, project_id: str) -> dict:
        return self._request_or_raise(
            "GET", f"/api/planner/projects/{project_id}", not_found_message=f"no such project: {project_id}"
        )

    def get_team(self, team_id: str) -> dict:
        return self._request_or_raise(
            "GET", f"/api/planner/teams/{team_id}", not_found_message=f"no such team: {team_id}"
        )

    def list_quotes(self) -> list:
        return self._request_or_raise("GET", "/api/planner/quotes")

    def get_quote(self, quote_id: str) -> dict:
        return self._request_or_raise(
            "GET", f"/api/planner/quotes/{quote_id}", not_found_message=f"no such quote: {quote_id}"
        )

    # -- writes ---------------------------------------------------------------

    def create_project(self, body: dict, actor_email: str) -> dict:
        # POST /api/planner/projects -- assumed request shape {"body": ..., "actorEmail": ...},
        # assumed response {"id": ..., "ver": ...} matching the mock.
        return self._request_or_raise(
            "POST", "/api/planner/projects", json_body={"body": body, "actorEmail": actor_email}
        )

    def update_project(self, project_id: str, body: dict, ver: int, actor_email: str) -> dict:
        # PUT /api/planner/projects/<id> -- optimistic concurrency per
        # starthere/conventions/coding-conventions.md: send the ver we last
        # read; a 409 means someone else wrote first. Docstring on the ABC
        # method says "may raise on 409 (stale ver)" -- mirror MockPlannerAdapter
        # by raising ValueError (not a bespoke HTTP exception) so callers in
        # interactions.py don't need an adapter-specific except clause.
        resp = self._request(
            "PUT",
            f"/api/planner/projects/{project_id}",
            json_body={"body": body, "ver": ver, "actorEmail": actor_email},
        )
        if resp.status_code == 404:
            raise KeyError(f"no such project: {project_id}")
        if resp.status_code == 409:
            raise ValueError(f"stale ver for {project_id}: server rejected ver {ver}")
        resp.raise_for_status()
        return resp.json()

    def allocate_quote_number(self) -> int:
        # POST /api/planner/quote-number -- the atomic, server-issued counter.
        # Never invent a quote number client-side (handbook 2.5). Assumed
        # response shape: {"quoteNumber": <int>}.
        data = self._request_or_raise("POST", "/api/planner/quote-number")
        return int(data["quoteNumber"])

    def create_quote(self, body: dict, actor_email: str) -> dict:
        return self._request_or_raise(
            "POST", "/api/planner/quotes", json_body={"body": body, "actorEmail": actor_email}
        )

    def transition_quote(self, quote_id: str, to_status: str, ver: int, actor_email: str, note: str | None = None) -> dict:
        # Defense in depth (guardrail 3.7): check the role bot-side BEFORE
        # calling the real transition endpoint, even though planner_api.py's
        # transition handler is expected to enforce this too and remains the
        # single source of truth. This costs two extra reads (get_quote,
        # get_users) that MockPlannerAdapter doesn't need since it already
        # holds everything in memory -- acceptable for a low-traffic bot.
        quote = self.get_quote(quote_id)
        from_status = quote["body"].get("approvalStatus", "draft")
        role = self.get_users().get(actor_email, {}).get("role", "member")
        if not can_act_on_transition(role, from_status, to_status):
            raise TransitionNotAllowed(f"{actor_email} ({role}) cannot move {from_status} -> {to_status}")

        resp = self._request(
            "POST",
            f"/api/planner/quotes/{quote_id}/transition",
            json_body={"toStatus": to_status, "ver": ver, "actorEmail": actor_email, "note": note},
        )
        if resp.status_code == 404:
            raise KeyError(f"no such quote: {quote_id}")
        if resp.status_code == 409:
            raise ValueError(f"stale ver for {quote_id}: server rejected ver {ver}")
        if resp.status_code == 403:
            raise TransitionNotAllowed(f"server refused {from_status} -> {to_status} for {actor_email}")
        resp.raise_for_status()
        return resp.json()


def build_adapter(kind: str, *, base_url: str | None = None) -> PlannerAdapter:
    if kind == "mock":
        return MockPlannerAdapter()
    if kind == "real":
        if not base_url:
            raise ValueError("PLANNER_ADAPTER=real requires EMBLAZE_BASE_URL")
        return RealPlannerAdapter(base_url)
    raise ValueError(f"unknown PLANNER_ADAPTER: {kind!r}")
