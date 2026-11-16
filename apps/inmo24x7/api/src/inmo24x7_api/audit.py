"""inmo24x7's own audit actions (core's audit log stores any product's actions as strings).
Details are ids, codes and counts only."""

from enum import StrEnum


class InmoAction(StrEnum):
    CONDITION_SETTINGS_SAVED = "condition_settings_saved"
    CONDITION_MATCH_OVERRIDDEN = "condition_match_overridden"
