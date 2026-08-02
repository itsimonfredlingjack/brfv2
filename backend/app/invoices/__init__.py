"""Fakturor: one invoice as one coherent case, not a row of accounting data.

The integration block already reads an invoice out of a system the association
already has (:mod:`app.integrations`) and compares it against the association's
own documents. What it does not do is hold the *case*: the thing a board member
opens, which has to say what the invoice is, what changed, what it was compared
against, what is missing, who is looking at it and what happened so far.

This package is that case, and it deliberately owns almost no data of its own:

* the invoice itself is still an :class:`~app.integrations.models.InvoiceSnapshot`
  produced by a read-only adapter;
* the analysis is still a :class:`~app.integrations.models.ReviewFinding` with
  verbatim-verified citations;
* work is still an :mod:`app.tasks` uppgift;
* the original file is still an ordinary document of the association's.

What is new is :class:`~app.invoices.models.InvoiceCase` — the stable identity
that several observations of the same invoice converge on, the local review
status this product owns (which is emphatically *not* an approval in anyone
else's system), and the timeline that keeps machine findings and human
decisions apart while showing them in one order.
"""

from __future__ import annotations

__all__ = ["models", "identity", "compare", "cases", "routes"]
