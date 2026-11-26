"""inmo24x7's own audit actions (core's audit log stores any product's actions as strings).
Details are ids, codes and counts only."""

from enum import StrEnum


class InmoAction(StrEnum):
    CONDITION_SETTINGS_SAVED = "condition_settings_saved"
    CONDITION_MATCH_OVERRIDDEN = "condition_match_overridden"
    # Privacy requests (privacy/): counts only, never the phone, the name or a hash of them.
    CONTACT_DATA_DELETED = "contact_data_deleted"
    ACCOUNT_CLOSURE_REQUESTED = "account_closure_requested"
    ACCOUNT_CLOSED = "account_closed"
    # Integrations (integrations/): which one ("kind": tokko / webhook / widget), never a key.
    INTEGRATION_CONNECTED = "integration_connected"
    INTEGRATION_UPDATED = "integration_updated"
    INTEGRATION_DISCONNECTED = "integration_disconnected"
    # "Cargar desde un link" (properties/): one publication read ("code": read, text or the
    # problem; "source": structured / model / both / none). Never the link. Also the
    # per-agency rate limit's count.
    PROPERTY_LINK_READ = "property_link_read"
    # The lead agent (leads/graph.py): the model was down on a message's last attempt, so the
    # conversation went to the team with a fixed reply. Codes only ("reason"), never text.
    AGENT_FAILURE_HAND_OFF = "agent_failure_hand_off"
