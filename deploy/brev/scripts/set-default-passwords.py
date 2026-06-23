#!/usr/bin/env python3
"""Set default application account passwords from process environment."""

import asyncio
import os
from datetime import datetime

import asyncpg
import bcrypt


def read_password(env_name: str) -> str:
    value = os.getenv(env_name, "")
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{env_name} must contain ASCII characters only") from exc

    if len(encoded) > 72:
        raise ValueError(f"{env_name} must be 72 bytes or fewer for bcrypt")

    return value


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("ascii"), bcrypt.gensalt()).decode("ascii")


async def ensure_users_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            full_name VARCHAR(100) NOT NULL,
            hashed_password VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'user',
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );
        """
    )


async def upsert_user(
    conn: asyncpg.Connection,
    username: str,
    email: str,
    full_name: str,
    role: str,
    password: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO users (
            username, email, full_name, hashed_password, role, status, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, 'active', $6, $6)
        ON CONFLICT (username) DO UPDATE
        SET email = EXCLUDED.email,
            full_name = EXCLUDED.full_name,
            hashed_password = EXCLUDED.hashed_password,
            role = EXCLUDED.role,
            status = 'active',
            updated_at = EXCLUDED.updated_at;
        """,
        username,
        email,
        full_name,
        hash_password(password),
        role,
        datetime.utcnow(),
    )


async def main() -> None:
    admin_password = read_password("ADMIN_PASSWORD")
    user_password = read_password("USER_PASSWORD")

    if not admin_password and not user_password:
        print("No passwords provided. Nothing to update.")
        return

    conn = await asyncpg.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5435")),
        user=os.getenv("POSTGRES_USER", "warehouse"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        database=os.getenv("POSTGRES_DB", "warehouse"),
    )

    try:
        await ensure_users_table(conn)
        updated = []
        if admin_password:
            await upsert_user(
                conn,
                "admin",
                "admin@warehouse.com",
                "System Administrator",
                "admin",
                admin_password,
            )
            updated.append("admin")

        if user_password:
            await upsert_user(
                conn,
                "user",
                "user@warehouse.com",
                "Regular User",
                "operator",
                user_password,
            )
            updated.append("user")
    finally:
        await conn.close()

    print("Updated passwords for: " + ", ".join(updated) + ".")


if __name__ == "__main__":
    asyncio.run(main())
