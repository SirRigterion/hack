#!/usr/bin/env bash

set -e

echo "Run apply migrations.."
alembic heads
alembic upgrade head
alembic heads
echo "Migrations applied!"

exec "$@"