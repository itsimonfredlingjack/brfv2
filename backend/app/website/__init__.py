"""Hemsidan: the association's public website, built inside the product.

A BRF that already keeps its documents, its post, its invoices and its
obligations here can also publish the page its members actually read — without
a second system, a second login, or a second place for a fact to be wrong.

Three things make this more than a page builder, and each of them is a
constraint the rest of the package exists to enforce:

- **A page is structured data, not HTML.** Blocks of declared types with
  declared fields (:mod:`app.website.components`), stored as this product's own
  schema-versioned JSON (:mod:`app.website.models`) and rendered by the same
  React components in the editor and on the published site.
- **There is exactly one way to change anything.** A person dragging a section
  and the AI partner rewriting a paragraph both emit commands into
  :mod:`app.website.commands`, which validates and applies them under the
  store's lock. No caller ever sends a page back to be stored as-is.
- **The grounding invariant survives contact with a blank page.** Text a model
  wrote that asserts something about the association must trace to the
  association's own documents, verified through the ordinary answer pipeline,
  or it is refused and nothing is written (:mod:`app.website.grounding`).

Editing happens in a draft; publishing cuts an immutable revision; the public
sees a published revision; rollback republishes an earlier one. Nothing a model
does reaches the public, because publishing is not in the command vocabulary at
all.
"""

from .commands import CommandContext, CommandRefused, apply_command, parse_commands
from .components import COMPONENTS, vocabulary
from .models import (
    SCHEMA_VERSION,
    Block,
    PageDraft,
    PageRevision,
    Publication,
    Site,
    SitePage,
    SiteTransaction,
)
from .store import WebsiteStore, WebsiteStoreError

__all__ = [
    "COMPONENTS",
    "SCHEMA_VERSION",
    "Block",
    "CommandContext",
    "CommandRefused",
    "PageDraft",
    "PageRevision",
    "Publication",
    "Site",
    "SitePage",
    "SiteTransaction",
    "WebsiteStore",
    "WebsiteStoreError",
    "apply_command",
    "parse_commands",
    "vocabulary",
]
