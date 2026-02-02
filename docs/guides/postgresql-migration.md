# PostgreSQL Migration Guide

This guide covers migrating from SQLite (development) to PostgreSQL (production).

## Prerequisites

- PostgreSQL 16+ installed
- psycopg[binary] already in requirements.txt

## Step 1: Create PostgreSQL Database

Using pgAdmin or psql:

```sql
-- Connect as postgres superuser, then run:
CREATE USER papertrail WITH PASSWORD 'your-secure-password';
CREATE DATABASE papertrail OWNER papertrail;

-- Connect to the papertrail database and grant schema permissions
\c papertrail
GRANT ALL ON SCHEMA public TO papertrail;
```

Or using pgAdmin GUI:
1. Right-click "Login/Group Roles" → Create → Login/Group Role
2. Name: `papertrail`, set password in Definition tab
3. Right-click "Databases" → Create → Database
4. Name: `papertrail`, Owner: `papertrail`

## Step 2: Update Environment Variable

Edit your `.env` file:

```bash
# Change from SQLite (default) to PostgreSQL
DATABASE_URL=postgres://papertrail:your-secure-password@localhost:5432/papertrail
```

## Step 3: Export Data from SQLite (Optional)

If you have existing data to migrate:

```powershell
.\venv\Scripts\Activate.ps1

# Export data to JSON fixtures
python manage.py dumpdata --exclude auth.permission --exclude contenttypes > data_backup.json
```

## Step 4: Run Migrations on PostgreSQL

```powershell
.\venv\Scripts\Activate.ps1

# Verify connection
python manage.py check

# Apply migrations
python manage.py migrate

# Verify tables created
python manage.py showmigrations
```

## Step 5: Import Data (If Migrating Existing Data)

```powershell
# Load the backup data
python manage.py loaddata data_backup.json
```

## Step 6: Create Superuser (If Fresh Install)

```powershell
python manage.py createsuperuser
```

## Verification

```powershell
# Check database connection
python manage.py dbshell

# In psql, verify tables:
\dt

# Exit with:
\q
```

## PostgreSQL-Specific Features

Once on PostgreSQL, you can enable these features:

### Full-Text Search

Add to models that need search:

```python
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex

class Package(models.Model):
    title = models.CharField(max_length=255)
    search_vector = SearchVectorField(null=True)

    class Meta:
        indexes = [
            GinIndex(fields=['search_vector']),
        ]
```

### JSON Field Lookups

PostgreSQL supports advanced JSON queries:

```python
# Query JSON fields
Office.objects.filter(permissions__can_approve=True)
```

## Troubleshooting

### Connection Refused
- Ensure PostgreSQL service is running
- Check pg_hba.conf allows local connections
- Verify port 5432 is not blocked

### Permission Denied
- Ensure user has CONNECT privilege on database
- Grant schema permissions: `GRANT ALL ON SCHEMA public TO papertrail;`

### Encoding Issues
- Create database with UTF-8: `CREATE DATABASE papertrail WITH ENCODING 'UTF8';`

## Production Recommendations

1. **Use connection pooling** (PgBouncer or Django's CONN_MAX_AGE)
2. **Set up SSL** for database connections
3. **Regular backups** with pg_dump
4. **Monitor** with pg_stat_statements

```python
# Production database settings example
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST"),
        "PORT": env("DB_PORT", default="5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {
            "sslmode": "require",
        },
    }
}
```
