import re

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_user(display_name: str) -> str:
    """Derives a stable user key from a display name.

    We can't resolve a real Slack user id purely from the rendered DOM, so
    the display name (normalized) stands in as the user's identity. This
    means a user renaming themselves will show up as a "new" user in the
    archive — acceptable for the MVP.
    """
    slug = _SLUG_RE.sub("-", display_name.strip().lower()).strip("-")
    return slug or "unknown"
