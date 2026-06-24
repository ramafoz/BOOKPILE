from __future__ import annotations

import argparse
import html
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from difflib import SequenceMatcher

from common import connect_read_only, report_path, write_csv


USER_AGENT = "BOOKPILE Goodreads link auditor/1.0 (personal local catalogue)"
TITLE_PATTERN = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
    re.IGNORECASE,
)
HTML_TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
JSON_NAME_PATTERN = re.compile(r'"name"\s*:\s*"([^"]+)"')
AUTHOR_PATTERN = re.compile(
    r'"author"\s*:\s*(?:\[[^\]]*?"name"\s*:\s*"([^"]+)"|'
    r'\{[^}]*?"name"\s*:\s*"([^"]+)")',
    re.I | re.S,
)


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", html.unescape(value))
    value = "".join(
        character for character in value
        if not unicodedata.combining(character)
    )
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def similarity(expected: str, actual: str) -> float:
    left = normalized(expected)
    right = normalized(actual)
    if not left or not right:
        return 0
    if left in right or right in left:
        return 1
    return SequenceMatcher(None, left, right).ratio()


def canonical_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    hostname = (parsed.hostname or "").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit(
        ("https", f"{hostname}{port}", path, "", "")
    )


def duplicate_groups(books: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for book in books:
        grouped.setdefault(canonical_url(book["goodreads_url"]), []).append(book)
    return {
        url: members
        for url, members in grouped.items()
        if len(members) > 1
    }


def extract_metadata(body: str) -> tuple[str, str]:
    title_match = TITLE_PATTERN.search(body) or HTML_TITLE_PATTERN.search(body)
    title = html.unescape(title_match.group(1)).strip() if title_match else ""
    if title.endswith(" | Goodreads"):
        title = title.removesuffix(" | Goodreads").strip()

    author_match = AUTHOR_PATTERN.search(body)
    author = (
        next((group for group in author_match.groups() if group), "")
        if author_match
        else ""
    )
    if not title:
        name_match = JSON_NAME_PATTERN.search(body)
        title = html.unescape(name_match.group(1)).strip() if name_match else ""
    return title, html.unescape(author).strip()


def check_link(book: dict, timeout: float) -> dict:
    url = book["goodreads_url"]
    result = {
        "status": "",
        "book_id": book["id"],
        "expected_title": book["title"],
        "expected_author": book["author"],
        "url": url,
        "canonical_url": canonical_url(url),
        "duplicate_books": "",
        "http_status": "",
        "final_url": "",
        "page_title": "",
        "page_author": "",
        "title_similarity": "",
        "author_similarity": "",
        "message": "",
    }
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme not in {"http", "https"}
        or not (
            hostname == "goodreads.com"
            or hostname.endswith(".goodreads.com")
        )
    ):
        result.update(
            status="INVALID_URL",
            message="URL is not an HTTP(S) Goodreads address.",
        )
        return result

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(500_000).decode("utf-8", errors="replace")
            result["http_status"] = response.status
            result["final_url"] = response.geturl()
    except urllib.error.HTTPError as error:
        result.update(
            status="HTTP_ERROR",
            http_status=error.code,
            final_url=error.geturl(),
            message=f"Goodreads returned HTTP {error.code}.",
        )
        return result
    except Exception as error:
        result.update(
            status="UNREACHABLE",
            message=f"{type(error).__name__}: {error}",
        )
        return result

    if "/user/sign_in" in result["final_url"]:
        result.update(
            status="MANUAL_REVIEW",
            message=(
                "Review link exists but Goodreads requires a signed-in browser "
                "to reveal the associated book."
            ),
        )
        return result

    page_title, page_author = extract_metadata(body)
    result["page_title"] = page_title
    result["page_author"] = page_author
    title_score = similarity(book["title"], page_title)
    author_score = similarity(book["author"], page_author)
    result["title_similarity"] = f"{title_score:.2f}"
    result["author_similarity"] = f"{author_score:.2f}"

    if not page_title:
        result.update(
            status="UNVERIFIED",
            message="Page responded but no reliable book metadata was found.",
        )
    elif title_score >= 0.78 and (not page_author or author_score >= 0.55):
        result.update(
            status="MATCH",
            message="Goodreads metadata matches the catalogue.",
        )
    else:
        result.update(
            status="POSSIBLE_MISMATCH",
            message="Goodreads metadata does not closely match title or author.",
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only audit of BOOKPILE Goodreads links."
    )
    parser.add_argument("--timeout", type=float, default=12)
    parser.add_argument("--limit", type=int, default=0, help="Check only N links.")
    parser.add_argument(
        "--duplicates-only",
        action="store_true",
        help="Check URL uniqueness without making network requests.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Open unverifiable links one at a time for signed-in review.",
    )
    args = parser.parse_args()

    with connect_read_only() as connection:
        rows = connection.execute(
            """
            SELECT id, title, author, goodreads_url
            FROM books
            WHERE goodreads_url IS NOT NULL
              AND trim(goodreads_url) <> ''
            ORDER BY title COLLATE NOCASE, author COLLATE NOCASE
            """
        ).fetchall()
    all_books = [dict(row) for row in rows]
    duplicates = duplicate_groups(all_books)
    duplicate_book_count = sum(len(members) for members in duplicates.values())
    print(
        f"Unique-link check: {len(duplicates)} duplicate groups, "
        f"{duplicate_book_count} affected books."
    )
    for members in duplicates.values():
        titles = ", ".join(
            f'#{book["id"]} {book["title"]}'
            for book in members
        )
        print(f"  DUPLICATE: {titles}")

    books = all_books[: args.limit or None]
    print(f"Checking {len(books)} Goodreads links. This can take a few minutes.")

    results = []
    stopped_early = False
    for index, book in enumerate(books, start=1):
        canonical = canonical_url(book["goodreads_url"])
        duplicate_members = duplicates.get(canonical, [])
        if duplicate_members:
            result = {
                "status": "DUPLICATE_URL",
                "book_id": book["id"],
                "expected_title": book["title"],
                "expected_author": book["author"],
                "url": book["goodreads_url"],
                "canonical_url": canonical,
                "duplicate_books": " | ".join(
                    f'#{member["id"]} {member["title"]}'
                    for member in duplicate_members
                    if member["id"] != book["id"]
                ),
                "http_status": "",
                "final_url": "",
                "page_title": "",
                "page_author": "",
                "title_similarity": "",
                "author_similarity": "",
                "message": "The same Goodreads URL is assigned to multiple books.",
            }
        elif args.duplicates_only:
            continue
        else:
            result = check_link(book, args.timeout)
        results.append(result)
        print(f'[{index}/{len(books)}] {result["status"]}: {book["title"]}')
        if args.interactive and result["status"] in {
            "MANUAL_REVIEW",
            "POSSIBLE_MISMATCH",
            "UNVERIFIED",
        }:
            webbrowser.open(result["url"], new=2)
            while True:
                answer = input(
                    "Does the Goodreads page match this book? "
                    "[y]es / [n]o / [s]kip / [q]uit: "
                ).strip().lower()
                if answer in {"y", "yes"}:
                    result["status"] = "MANUAL_MATCH"
                    result["message"] = "Confirmed manually in signed-in browser."
                    break
                if answer in {"n", "no"}:
                    result["status"] = "MANUAL_MISMATCH"
                    result["message"] = "Rejected manually in signed-in browser."
                    break
                if answer in {"s", "skip", ""}:
                    result["status"] = "MANUAL_REVIEW"
                    result["message"] = "Skipped during manual review."
                    break
                if answer in {"q", "quit"}:
                    result["status"] = "MANUAL_REVIEW"
                    result["message"] = "Manual review stopped here."
                    stopped_early = True
                    break
                print("Please enter y, n, s, or q.")
            if stopped_early:
                break

    if not results:
        if not books:
            print("No Goodreads links found.")
        elif args.duplicates_only:
            print("All Goodreads links are unique.")
        return 0

    path = report_path("goodreads-audit")
    write_csv(path, results[0].keys(), results)
    counts: dict[str, int] = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1

    print("\nResults:")
    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")
    print(f"CSV report: {path}")
    return 1 if any(
        result["status"] in {
            "INVALID_URL",
            "HTTP_ERROR",
            "POSSIBLE_MISMATCH",
            "MANUAL_MISMATCH",
            "DUPLICATE_URL",
        }
        for result in results
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
