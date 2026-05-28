"""
Stub out heavy external modules before any test imports them.
Only stubs libs that are broken in this sandbox (google-auth crypto, psycopg2).
email_classifier and pricing_engine are NOT stubbed here — tests import them directly.
"""

import sys
import types
from unittest.mock import MagicMock

# Stub google auth / gmail modules to avoid crypto import errors
for mod in [
    "google",
    "google.auth",
    "google.auth.transport",
    "google.auth.transport.requests",
    "google.oauth2",
    "google.oauth2.credentials",
    "google_auth_oauthlib",
    "google_auth_oauthlib.flow",
    "googleapiclient",
    "googleapiclient.discovery",
    "psycopg2",
    "psycopg2.extras",
    "psycopg2.extensions",
]:
    sys.modules.setdefault(mod, MagicMock())

# Stub gmail_client so negotiation_engine can be imported
gmail_stub = types.ModuleType("gmail_client")
gmail_stub.send_reply = MagicMock()
gmail_stub.mark_as_read = MagicMock()
gmail_stub.get_unread_messages_in_thread = MagicMock(return_value=[])
gmail_stub.get_unread_messages_from_email = MagicMock(return_value=[])
sys.modules["gmail_client"] = gmail_stub

# Stub state_store so negotiation_engine can be imported
state_store_stub = types.ModuleType("state_store")
state_store_stub.upsert_creator = MagicMock()
state_store_stub.get_active_creators = MagicMock(return_value=[])
state_store_stub.get_creators_needing_followup = MagicMock(return_value=[])
sys.modules["state_store"] = state_store_stub
