"""Paper lookup tools backed by the free OpenAlex API (adapted from ykdojo/paper-search).

In a real deployment this module is the stand-in for your own data source: an internal
database, docs, or search engine living in the same infra.
"""
import urllib.parse
import urllib.request
import json
import time

MAILTO = "paper-search@example.com"
UNAVAILABLE = (
    "The paper search service is temporarily unavailable. Tell the user and suggest trying again "
    "in a moment; do not invent papers."
)


def _get(url: str) -> dict:
    """GET with a couple of retries: OpenAlex throws occasional 5xx, and a transient
    failure should not kill the whole agent turn."""
    last_error = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": f"gemma-voice-agent (mailto:{MAILTO})"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.load(resp)
        except Exception as e:  # noqa: BLE001
            last_error = e
            time.sleep(1.0 * (attempt + 1))
    raise last_error


def _abstract_from_inverted_index(inv: dict | None, limit: int = 400) -> str:
    if not inv:
        return "N/A"
    positions = [(pos, word) for word, poss in inv.items() for pos in poss]
    text = " ".join(word for _, word in sorted(positions))
    return text[:limit]


def search_papers(query: str, limit: int = 5, sort: str = "relevance") -> str:
    """Search academic papers by keyword. sort: relevance | cites | date."""
    sort_map = {
        "relevance": "relevance_score:desc",
        "cites": "cited_by_count:desc",
        "date": "publication_date:desc",
    }
    url = (
        "https://api.openalex.org/works?search=" + urllib.parse.quote(query)
        + f"&per_page={min(int(limit), 10)}&sort={sort_map.get(sort, sort_map['relevance'])}&mailto={MAILTO}"
    )
    try:
        data = _get(url)
    except Exception:  # noqa: BLE001 - degrade instead of killing the turn
        return UNAVAILABLE
    lines = []
    for i, work in enumerate(data.get("results", []), 1):
        authors = ", ".join(a["author"]["display_name"] for a in work.get("authorships", [])[:3])
        lines.append(
            f"{i}. [{work.get('cited_by_count', 0)} cites] ({work.get('publication_year')}) {work.get('title')}\n"
            f"   Authors: {authors}\n"
            f"   DOI: {work.get('doi') or 'N/A'}\n"
            f"   Abstract: {_abstract_from_inverted_index(work.get('abstract_inverted_index'))}"
        )
    return "\n".join(lines) or "No results found."


def get_paper(doi_or_openalex_id: str) -> str:
    """Get full details for one paper by DOI (e.g. https://doi.org/10...) or OpenAlex ID (e.g. W2789811475)."""
    ident = doi_or_openalex_id.strip()
    if ident.startswith("W"):
        url = f"https://api.openalex.org/works/{ident}?mailto={MAILTO}"
    else:
        doi = ident.removeprefix("https://doi.org/")
        url = f"https://api.openalex.org/works/doi:{urllib.parse.quote(doi)}?mailto={MAILTO}"
    try:
        w = _get(url)
    except Exception:  # noqa: BLE001 - degrade instead of killing the turn
        return UNAVAILABLE
    authors = ", ".join(a["author"]["display_name"] for a in w.get("authorships", [])[:10])
    return (
        f"{w.get('title')}\nYear: {w.get('publication_year')}\nAuthors: {authors}\n"
        f"Cited by: {w.get('cited_by_count')}\nDOI: {w.get('doi') or 'N/A'}\n"
        f"Abstract: {_abstract_from_inverted_index(w.get('abstract_inverted_index'), 1500)}"
    )
