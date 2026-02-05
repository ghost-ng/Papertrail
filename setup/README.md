# Papertrail Setup Scripts

This folder contains scripts for setting up the Papertrail development environment.

## Quick Start

Run the full setup script to set up everything at once:

```powershell
.\setup\full_setup.ps1
```

This will:
1. Generate environment keys (.env file)
2. Run database migrations
3. Create mock data (3 organizations, 30+ offices, 150+ users)
4. Setup admin permission group

## Individual Scripts

### Generate Environment Keys

Generates Django SECRET_KEY and other security keys.

```powershell
# Print keys to console
.\setup\generate_env_keys.ps1

# Create .env file in project root
.\setup\generate_env_keys.ps1 -EnvFile

# Include DEBUG=True for development
.\setup\generate_env_keys.ps1 -EnvFile -IncludeDebug

# Append to existing file
.\setup\generate_env_keys.ps1 -EnvFile -Append
```

Or use Django manage.py directly:

```powershell
python manage.py generate_env_keys --help
python manage.py generate_env_keys --env-file --include-debug
```

### Create Mock Data

Creates realistic mock data for development and testing.

```powershell
# Create with default settings (5 users per office)
.\setup\create_mock_data.ps1

# Customize users per office
.\setup\create_mock_data.ps1 -UsersPerOffice 10

# Set custom password for all mock users
.\setup\create_mock_data.ps1 -Password "mydevpassword"

# Clear existing mock data before creating new
.\setup\create_mock_data.ps1 -Clear

# Preview what would be created (dry run)
.\setup\create_mock_data.ps1 -DryRun
```

Or use Django manage.py directly:

```powershell
python manage.py create_mock_data --help
python manage.py create_mock_data --users-per-office 10 --password "mypassword"
```

## Mock Data Structure

The `create_mock_data` command creates:

### Organizations (3)
- **ACME** - ACME Corporation (business)
- **GOV** - Federal Government Agency
- **EDU** - State University

### Offices per Organization (10-11 each)

**ACME Corporation:**
- HQ (Headquarters)
- FIN (Finance Division)
- ENG (Engineering Division)
  - SWDEV (Software Development)
  - HWDEV (Hardware Development)
  - QA (Quality Assurance)
- HR (Human Resources)
- SALES (Sales & Marketing)
  - MKTG (Marketing)
  - SUPP (Customer Support)
- LEGAL (Legal Department)

**Government Agency:**
- EXEC (Executive Office)
- OPS (Operations)
- REG (Regulatory Affairs)
  - PERMIT (Permits & Licensing)
  - ENFORCE (Enforcement)
- IT (Information Technology)
  - SECOPS (Security Operations)
  - NETOPS (Network Operations)
- ADMIN (Administrative Services)
- COMPL (Compliance)

**State University:**
- PROV (Provost Office)
- ACAD (Academic Affairs)
  - ENG (School of Engineering)
  - SCI (School of Science)
  - ARTS (School of Arts)
- RES (Research Office)
- STU (Student Services)
  - REG (Registrar)
  - AID (Financial Aid)
- FADM (Finance & Administration)
- LIB (University Library)

### Users

- 5 users per office by default (configurable)
- First user in each office is an **office manager**
- First user in each organization is an **org manager**
- All users have approved organization and office memberships
- Email domains: `@acme.com`, `@gov.agency.gov`, `@university.edu`

## Default Credentials

- **Password**: `password123` (configurable)
- Sample emails are shown in the command output after creation

## Environment Keys Generated

The `generate_env_keys` command creates:

- `SECRET_KEY` - Django's cryptographic signing key
- `DB_ENCRYPTION_KEY` - For encrypting sensitive database fields
- `INTERNAL_API_KEY` - For service-to-service communication

Plus commented-out templates for:
- Database URL (PostgreSQL)
- Email settings (SMTP)
- Allowed hosts
