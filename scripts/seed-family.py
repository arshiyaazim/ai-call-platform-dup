#!/usr/bin/env python3
"""
Fazle — Seed Family Data
Creates the admin (Azim) and sample family member accounts.
Run once after first deploy or to reset test data.

Usage:
    python seed-family.py                         # uses defaults
    FAZLE_DATABASE_URL=postgres://... python seed-family.py
"""
import os
import sys
import uuid

import psycopg2
import psycopg2.extras
from passlib.context import CryptContext

psycopg2.extras.register_uuid()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DATABASE_URL = os.getenv(
    "FAZLE_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/postgres",
)

# ── Family members to seed ──────────────────────────────────
FAMILY = [
    {
        "email": "azim@iamazim.com",
        "password": "ChangeMe123!",
        "name": "Azim",
        "relationship_to_azim": "self",
        "role": "admin",
    },
    {
        "email": "wife@iamazim.com",
        "password": "ChangeMe123!",
        "name": "Sajeda Yesmin",
        "relationship_to_azim": "wife",
        "role": "member",
    },
    {
        "email": "daughter@iamazim.com",
        "password": "ChangeMe123!",
        "name": "Arshiya Wafiqah",
        "relationship_to_azim": "daughter",
        "role": "member",
    },
]


def seed():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for member in FAMILY:
                # Skip if email already exists
                cur.execute(
                    "SELECT id FROM fazle_users WHERE email = %s",
                    (member["email"],),
                )
                if cur.fetchone():
                    print(f"  ✓ {member['name']} ({member['email']}) already exists — skipped")
                    continue

                user_id = uuid.uuid4()
                hashed = pwd_context.hash(member["password"])
                cur.execute(
                    """
                    INSERT INTO fazle_users (id, email, hashed_password, name, relationship_to_azim, role)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        member["email"],
                        hashed,
                        member["name"],
                        member["relationship_to_azim"],
                        member["role"],
                    ),
                )
                print(f"  ✓ Created {member['name']} ({member['email']}) — {member['role']}")

        conn.commit()
        print("\nSeed complete.")
    except Exception as e:
        conn.rollback()
        print(f"\n✗ Seed failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    print("Seeding Fazle family accounts...")
    print(f"Database: {DATABASE_URL.split('@')[-1]}\n")  # print host only, not creds
    seed()
