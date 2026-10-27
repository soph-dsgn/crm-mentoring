from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db.session import build_engine
from app.modules.legacy_io.service import restore_backup


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Restore a logical CRM backup into an empty database"
    )
    parser.add_argument("backup", type=Path)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--confirm-empty-business-data", action="store_true")
    args = parser.parse_args()
    if not args.confirm_empty_business_data:
        parser.error("--confirm-empty-business-data is required")
    url = make_url(args.database_url)
    if url.get_backend_name() == "postgresql" and not (url.database or "").endswith(
        ("_restore", "_test")
    ):
        parser.error("PostgreSQL restore database name must end with _restore or _test")
    backup = json.loads(args.backup.read_text(encoding="utf-8"))
    engine = build_engine(args.database_url)
    try:
        with Session(engine) as database, database.begin():
            counts = restore_backup(database, backup)
        print(json.dumps({"restored": counts}, sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
