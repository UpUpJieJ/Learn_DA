"""
Signed anonymous session — derives visitor_id from HttpOnly cookie.
"""

from uuid import uuid4

from fastapi import Request

ANONYMOUS_VISITOR_KEY = "anonymous_visitor_id"


def get_anonymous_visitor_id(request: Request) -> str:
    """Return a stable visitor ID from the signed session cookie.

    If no visitor ID exists in the session, one is generated and stored.
    """
    visitor_id = request.session.get(ANONYMOUS_VISITOR_KEY)
    if not isinstance(visitor_id, str):
        visitor_id = uuid4().hex
        request.session[ANONYMOUS_VISITOR_KEY] = visitor_id
    return visitor_id
