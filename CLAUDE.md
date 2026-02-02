# Claude Code Instructions for Papertrail

## Running Python Commands (Windows)

Always use PowerShell with proper quoting to activate the virtual environment and run commands:

```powershell
powershell -Command "cd 'c:\\Users\\miguel\\OneDrive\\Documents\\Papertrail'; .\\venv\\Scripts\\Activate.ps1; python manage.py <command>"
```

### Examples

**Run migrations:**
```powershell
powershell -Command "cd 'c:\\Users\\miguel\\OneDrive\\Documents\\Papertrail'; .\\venv\\Scripts\\Activate.ps1; python manage.py makemigrations"
powershell -Command "cd 'c:\\Users\\miguel\\OneDrive\\Documents\\Papertrail'; .\\venv\\Scripts\\Activate.ps1; python manage.py migrate"
```

**Run tests:**
```powershell
powershell -Command "cd 'c:\\Users\\miguel\\OneDrive\\Documents\\Papertrail'; .\\venv\\Scripts\\Activate.ps1; pytest -v"
```

**Run development server:**
```powershell
powershell -Command "cd 'c:\\Users\\miguel\\OneDrive\\Documents\\Papertrail'; .\\venv\\Scripts\\Activate.ps1; python manage.py runserver"
```

**Create superuser:**
```powershell
powershell -Command "cd 'c:\\Users\\miguel\\OneDrive\\Documents\\Papertrail'; .\\venv\\Scripts\\Activate.ps1; python manage.py createsuperuser"
```

## Project Structure

- `apps/` - Django applications
- `templates/` - Base templates
- `static/` - Static files (CSS, JS)
- `docs/` - Documentation and plans
- `papertrail/` - Django project settings

## Tech Stack

- Django 5.x
- SQLite (dev) / PostgreSQL (prod)
- Alpine.js 3.x (local, not CDN)
- Tailwind CSS 3.x

## Important Files

- `docs/PRODUCTION_BACKLOG.md` - Items deferred for production (Celery, Redis, Docker, etc.)
- `docs/plans/2025-01-30-document-routing-workflow-design.md` - Full system design document

## Skills to Use

When working on this project, leverage these skills:

### Development Workflow (superpowers)
- **superpowers:brainstorming** - For designing new features through collaborative dialogue
- **superpowers:writing-plans** - For creating detailed implementation plans in `docs/plans/`
- **superpowers:subagent-driven-development** - For executing plans with fresh subagents per task
- **superpowers:executing-plans** - For parallel session plan execution
- **superpowers:test-driven-development** - For TDD approach to implementation
- **superpowers:requesting-code-review** - For thorough code reviews
- **superpowers:finishing-a-development-branch** - For completing feature branches

### Frontend Design
- **frontend-design** - For UI/UX design decisions, component patterns, and accessibility
- Use Tailwind CSS utility classes
- Follow Alpine.js patterns for interactivity
- Ensure dark mode support with `dark:` variants
- Keep cards at uniform heights
- Use AJAX for user lookups and dynamic content

### Code Quality
- **code-reviewer** - For security-aware code reviews
- **code-architect** - For exploring complex codebases
- **performance-optimizer** - For identifying bottlenecks

### Backend
- **django-backend-expert** - For Django-specific implementations
- **python-backend-engineer** - For Python backend systems

## Design Patterns

### Admin Panel
- Hamburger menu for admin users in navbar
- Sidebar navigation in admin dashboard
- AJAX user search for adding members to offices/orgs
- Consolidated stats cards with uniform heights

### Permission Groups
- SystemAdminRequiredMixin - Full system access
- OrgAdminRequiredMixin - Organization-level access
- OfficeManagerRequiredMixin - Office-level access
