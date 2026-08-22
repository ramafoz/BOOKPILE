"""Read-only audit of legacy pile supports before BOOKPILE schema v8."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.visual_geometry import (  # noqa: E402
    AuditContainer,
    ContainerKind,
    LEGACY_SUPPORT_TOLERANCE,
    Rect,
    SupportKind,
    infer_pile_support,
)


def load_containers(database: Path) -> list[AuditContainer]:
    uri = f"file:{database.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                containers.id,
                containers.shelf_id,
                containers.layer,
                containers.container_type,
                visual.x,
                visual.y,
                visual.width,
                visual.height,
                (SELECT COUNT(*) FROM books
                 WHERE books.container_id = containers.id) AS book_count
            FROM containers
            JOIN visual_container_layout AS visual
              ON visual.container_id = containers.id
            ORDER BY containers.shelf_id, containers.layer,
                     containers.container_type, containers.container_number
            """
        ).fetchall()
    return [
        AuditContainer(
            id=row["id"],
            shelf_id=row["shelf_id"],
            layer=row["layer"],
            kind=ContainerKind(row["container_type"]),
            rect=Rect(row["x"], row["y"], row["width"], row["height"]),
            book_count=row["book_count"],
        )
        for row in rows
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "database",
        nargs="?",
        type=Path,
        default=BACKEND_ROOT / "data" / "bookpile.db",
    )
    args = parser.parse_args()
    containers = load_containers(args.database)
    piles = [item for item in containers if item.kind is ContainerKind.PILE]
    results = [
        (pile, infer_pile_support(pile, containers, LEGACY_SUPPORT_TOLERANCE))
        for pile in piles
    ]
    counts = Counter(result.kind.value for _, result in results)
    print(
        f"Read-only pile-support audit: {len(piles)} piles; "
        + ", ".join(f"{key.lower()}={value}" for key, value in sorted(counts.items()))
    )
    for pile, result in results:
        target = (
            f"row {result.container_id}"
            if result.kind is SupportKind.ROW
            else result.kind.value.lower()
        )
        print(
            f"pile {pile.id}: shelf={pile.shelf_id} layer={pile.layer} "
            f"books={pile.book_count} bottom={pile.rect.bottom:.3f} -> {target}"
        )
    unresolved = sum(
        result.kind in {SupportKind.AMBIGUOUS, SupportKind.INVALID}
        for _, result in results
    )
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
