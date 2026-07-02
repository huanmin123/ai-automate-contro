from __future__ import annotations


WINDOW_QUERY_FIELDS = {
    "title",
    "title_contains",
    "title_regex",
    "app",
    "process",
    "process_name",
    "class_name",
    "window_id",
    "match_index",
}

ELEMENT_LOCATOR_FIELDS = {
    "element_id",
    "automation_id",
    "name",
    "name_contains",
    "name_regex",
    "text",
    "text_contains",
    "text_regex",
    "control_type",
    "role",
    "element_class_name",
    "element_match_index",
}

ELEMENT_REQUIRED_LOCATOR_FIELDS = ELEMENT_LOCATOR_FIELDS - {"element_match_index"}
