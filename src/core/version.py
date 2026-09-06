"""The platform's single version string.

There used to be three, and they disagreed: `pyproject.toml` said `0.1.0` while both the FastAPI
app and the MCP docs server said `1.0.0`. Nothing derived one from another, so an API consumer
reading the OpenAPI schema and a developer reading the packaging metadata saw different answers.

Everything now imports this. `pyproject.toml` still carries its own literal because packaging
metadata is read before any of this code is importable — keep the two in step when releasing.

Versioning follows the docs changelog (`docs/changelog.md`): the minor version goes up when
behaviour changes in a way an operator has to know about, which given how this platform is used
includes anything that alters what a caller hears.
"""

__version__ = "1.2.0"
