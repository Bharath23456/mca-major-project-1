from getpass import getpass

from sqlalchemy import or_, select

from app.audit import record_audit
from app.auth import hash_password, validate_email, validate_username
from app.database import SessionLocal
from app.database_migrations import migrate_database
from app.models import User


def main() -> None:
    migrate_database()
    with SessionLocal() as session:
        if session.scalar(select(User.id).where(User.role == "ADMIN")) is not None:
            raise SystemExit("An administrator already exists; bootstrap is disabled.")

    try:
        username = validate_username(input("Administrator username: "))
        email = validate_email(input("Administrator email: "))
        password_input = getpass("Administrator password (12+ characters): ")
        if password_input != getpass("Confirm administrator password: "):
            raise ValueError("Passwords do not match.")
        password = hash_password(password_input)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    with SessionLocal() as session:
        if session.scalar(select(User.id).where(User.role == "ADMIN")) is not None:
            raise SystemExit("An administrator already exists; bootstrap is disabled.")
        if session.scalar(
            select(User.id).where(or_(User.username == username, User.email == email))
        ) is not None:
            raise SystemExit("A user already exists with that username or email.")
        user = User(
            username=username,
            email=email,
            password_hash=password,
            role="ADMIN",
            is_active=True,
        )
        session.add(user)
        session.flush()
        record_audit(
            session,
            user_id=user.id,
            action="admin_bootstrap",
            resource_type="user",
            resource_id=str(user.id),
            result="success",
        )
        session.commit()
        print(f"Administrator '{username}' created.")


if __name__ == "__main__":
    main()
