"""
backend/context_processors.py

Detects HTMX partial requests and injects the correct base template name
into every template context — no view changes required.

  Full page request  →  base_template = "base.html"        (full shell)
  HTMX partial       →  base_template = "base_partial.html" (content only)
"""


def htmx_base(request):
    is_htmx = request.headers.get("HX-Request") == "true"
    return {
        "base_template": "base_partial.html" if is_htmx else "base.html",
    }
