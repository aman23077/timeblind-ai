"""Create or rotate the persistent administrator recovery key."""

import argparse
import secrets
from sqlalchemy import func, select
from app.core.database import SessionLocal, initialize_database
from app.modules.users.models import User
from app.core.auth import AdminAccess, RecoveryKey, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", help="Existing account to grant administrator access")
    parser.add_argument("--admin", action="store_true", help="Grant administrator access to --email")
    parser.add_argument("--rotate", action="store_true", help="Replace the current universal key")
    args = parser.parse_args()
    if args.admin and not args.email:
        parser.error("--admin requires --email")
    initialize_database()
    with SessionLocal() as db:
        if args.admin:
            users = db.scalars(select(User).where(func.lower(User.email) == args.email.strip().lower())).all()
            if len(users) != 1:
                parser.error("Expected exactly one existing account for this email")
            if db.scalar(select(AdminAccess).where(AdminAccess.user_id == users[0].id)) is None:
                db.add(AdminAccess(user_id=users[0].id))
        existing = db.scalar(select(RecoveryKey).where(RecoveryKey.name == "universal"))
        if existing and not args.rotate:
            db.commit()
            print("A persistent recovery key is already configured. Use --rotate to replace it.")
            return
        token = secrets.token_urlsafe(32)
        if existing:
            existing.key_hash = digest(token)
        else:
            db.add(RecoveryKey(name="universal", key_hash=digest(token)))
        db.commit()
        print("Persistent recovery key for all accounts. It remains valid until rotated.")
        print(token)


if __name__ == "__main__":
    main()
