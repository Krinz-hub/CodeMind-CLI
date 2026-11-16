---
name: database-engineering
version: 1.0.0
description: Relational database schema design, migration management, foreign keys, index optimization, and query integrity.
category: database
triggers:
  manifests:
    - "alembic.ini"
    - "schema.prisma"
    - "migrations"
    - "sql"
  globs:
    - "*.sql"
    - "*migration*.py"
    - "*schema*.py"
  keywords:
    - "database"
    - "databases"
    - "sql"
    - "migration"
    - "migrations"
    - "schema"
    - "schemas"
    - "postgres"
    - "sqlite"
    - "mysql"
    - "index"
    - "indexes"
    - "indices"
    - "foreign key"
    - "foreign keys"
    - "query"
    - "queries"
required_tools:
  - read_file
  - create_file
  - apply_patch
  - run_command
dependencies: []
conflicts: []
workflow_steps:
  - "1. Inspect existing schema definitions, migrations, and ORM models (SQLAlchemy, Prisma, Django ORM, etc.)."
  - "2. Design relational schema with proper primary keys, foreign key constraints, and NOT NULL nullability rules."
  - "3. Author versioned, reversible database migration files (up and down operations)."
  - "4. Establish indexing strategies (B-Tree, BRIN, composite) for frequently queried foreign keys and filter columns."
  - "5. Verify that queries avoid N+1 anti-patterns using eager loading or batch lookups."
constraints:
  - "Never execute destructive column deletions (DROP COLUMN) in zero-downtime environments without phased deprecation."
  - "Always add indexes on foreign key columns used in joins to prevent sequential table scans."
  - "Ensure all database migrations have a matching rollback/down migration step."
verification:
  - "Run migration runner in dry-run/test mode and execute automated database integration tests."
enabled: true
---

# Database Engineering & Migrations Workflow

## 1. Schema Best Practices
- **Foreign Key Integrity:** Always enforce referential integrity at the database level (`ON DELETE CASCADE` or `ON DELETE RESTRICT`).
- **Data Types:** Choose optimal storage sizes (`BIGINT` for auto-incrementing IDs, `TIMESTAMPTZ` for UTC timestamps).
- **Composite Indexes:** When filtering by multiple fields (e.g. `tenant_id` and `created_at`), order index columns from highest to lowest cardinality.

## 2. Migration Protocol
1. Locate current migration sequence (`alembic/versions/` or `prisma/migrations/`).
2. Generate next sequential migration file.
3. Verify backward compatibility with existing application code.
