"""Management command to create mock data for development and testing."""

import random
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth.hashers import make_password

from apps.accounts.models import User
from apps.organizations.models import (
    Organization,
    Office,
    OrganizationMembership,
    OfficeMembership,
)


# Mock data definitions
ORGANIZATIONS = [
    {
        "code": "ACME",
        "name": "ACME Corporation",
        "description": "A multinational conglomerate specializing in innovative solutions.",
    },
    {
        "code": "GOV",
        "name": "Federal Government Agency",
        "description": "A federal agency responsible for regulatory oversight.",
    },
    {
        "code": "EDU",
        "name": "State University",
        "description": "A public research university with comprehensive programs.",
    },
]

# Office hierarchies per organization
OFFICE_STRUCTURES = {
    "ACME": [
        # Root offices
        {"code": "HQ", "name": "Headquarters", "parent": None},
        {"code": "FIN", "name": "Finance Division", "parent": None},
        {"code": "ENG", "name": "Engineering Division", "parent": None},
        {"code": "HR", "name": "Human Resources", "parent": None},
        {"code": "SALES", "name": "Sales & Marketing", "parent": None},
        {"code": "LEGAL", "name": "Legal Department", "parent": None},
        # Child offices under Engineering
        {"code": "SWDEV", "name": "Software Development", "parent": "ENG"},
        {"code": "HWDEV", "name": "Hardware Development", "parent": "ENG"},
        {"code": "QA", "name": "Quality Assurance", "parent": "ENG"},
        # Child offices under Sales
        {"code": "MKTG", "name": "Marketing", "parent": "SALES"},
        {"code": "SUPP", "name": "Customer Support", "parent": "SALES"},
    ],
    "GOV": [
        # Root offices
        {"code": "EXEC", "name": "Executive Office", "parent": None},
        {"code": "OPS", "name": "Operations", "parent": None},
        {"code": "REG", "name": "Regulatory Affairs", "parent": None},
        {"code": "IT", "name": "Information Technology", "parent": None},
        {"code": "ADMIN", "name": "Administrative Services", "parent": None},
        {"code": "COMPL", "name": "Compliance", "parent": None},
        # Child offices under Regulatory
        {"code": "PERMIT", "name": "Permits & Licensing", "parent": "REG"},
        {"code": "ENFORCE", "name": "Enforcement", "parent": "REG"},
        # Child offices under IT
        {"code": "SECOPS", "name": "Security Operations", "parent": "IT"},
        {"code": "NETOPS", "name": "Network Operations", "parent": "IT"},
    ],
    "EDU": [
        # Root offices
        {"code": "PROV", "name": "Provost Office", "parent": None},
        {"code": "ACAD", "name": "Academic Affairs", "parent": None},
        {"code": "RES", "name": "Research Office", "parent": None},
        {"code": "STU", "name": "Student Services", "parent": None},
        {"code": "FADM", "name": "Finance & Administration", "parent": None},
        {"code": "LIB", "name": "University Library", "parent": None},
        # Child offices under Academic Affairs
        {"code": "ENG", "name": "School of Engineering", "parent": "ACAD"},
        {"code": "SCI", "name": "School of Science", "parent": "ACAD"},
        {"code": "ARTS", "name": "School of Arts", "parent": "ACAD"},
        # Child offices under Student Services
        {"code": "REG", "name": "Registrar", "parent": "STU"},
        {"code": "AID", "name": "Financial Aid", "parent": "STU"},
    ],
}

# First and last names for generating users
FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Lisa", "Daniel", "Nancy",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
    "Kenneth", "Dorothy", "Kevin", "Carol", "Brian", "Amanda", "George", "Melissa",
    "Timothy", "Deborah", "Ronald", "Stephanie", "Edward", "Rebecca", "Jason", "Sharon",
    "Jeffrey", "Laura", "Ryan", "Cynthia", "Jacob", "Kathleen", "Gary", "Amy",
    "Nicholas", "Angela", "Eric", "Shirley", "Jonathan", "Anna", "Stephen", "Brenda",
    "Larry", "Pamela", "Justin", "Emma", "Scott", "Nicole", "Brandon", "Helen",
    "Benjamin", "Samantha", "Samuel", "Katherine", "Raymond", "Christine", "Gregory", "Debra",
    "Frank", "Rachel", "Alexander", "Carolyn", "Patrick", "Janet", "Jack", "Catherine",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas",
    "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White",
    "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young",
    "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz", "Parker",
    "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris", "Morales", "Murphy",
    "Cook", "Rogers", "Gutierrez", "Ortiz", "Morgan", "Cooper", "Peterson", "Bailey",
    "Reed", "Kelly", "Howard", "Ramos", "Kim", "Cox", "Ward", "Richardson",
    "Watson", "Brooks", "Chavez", "Wood", "James", "Bennett", "Gray", "Mendoza",
    "Ruiz", "Hughes", "Price", "Alvarez", "Castillo", "Sanders", "Patel", "Myers",
]


class Command(BaseCommand):
    help = "Create mock data for development: organizations, offices, users, and memberships"

    def add_arguments(self, parser):
        parser.add_argument(
            "--users-per-office",
            type=int,
            default=5,
            help="Number of users to create per office (default: 5)",
        )
        parser.add_argument(
            "--password",
            type=str,
            default="password123",
            help="Password for all created users (default: password123)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing mock data before creating new data",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without actually creating anything",
        )

    def generate_email(self, first_name, last_name, org_code, office_code):
        """Generate a unique email address."""
        domain = {
            "ACME": "acme.com",
            "GOV": "gov.agency.gov",
            "EDU": "university.edu",
        }.get(org_code, "example.com")

        base_email = f"{first_name.lower()}.{last_name.lower()}@{domain}"

        # Ensure uniqueness
        counter = 1
        email = base_email
        while User.objects.filter(email=email).exists():
            email = f"{first_name.lower()}.{last_name.lower()}{counter}@{domain}"
            counter += 1

        return email

    def create_user(self, first_name, last_name, email, password_hash, is_staff=False):
        """Create a user with the given details."""
        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=password_hash,
            is_staff=is_staff,
            is_active=True,
        )
        return user

    @transaction.atomic
    def handle(self, *args, **options):
        users_per_office = options["users_per_office"]
        password = options["password"]
        dry_run = options["dry_run"]
        clear = options["clear"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No data will be created"))
            self.stdout.write("")

        # Clear existing data if requested
        if clear and not dry_run:
            self.stdout.write("Clearing existing mock data...")
            # Only delete non-superuser accounts and mock organizations
            mock_org_codes = [org["code"] for org in ORGANIZATIONS]
            Organization.objects.filter(code__in=mock_org_codes).delete()
            # Delete users with mock email domains
            mock_domains = ["acme.com", "gov.agency.gov", "university.edu"]
            for domain in mock_domains:
                User.objects.filter(email__endswith=f"@{domain}").delete()
            self.stdout.write(self.style.SUCCESS("Cleared existing mock data"))

        # Pre-hash the password for efficiency
        password_hash = make_password(password)

        # Track statistics
        stats = {
            "organizations": 0,
            "offices": 0,
            "users": 0,
            "org_memberships": 0,
            "office_memberships": 0,
        }

        # Create organizations
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Creating Organizations..."))

        created_orgs = {}
        for org_data in ORGANIZATIONS:
            if dry_run:
                self.stdout.write(f"  Would create: {org_data['code']} - {org_data['name']}")
                created_orgs[org_data["code"]] = {"code": org_data["code"]}
            else:
                org, created = Organization.objects.get_or_create(
                    code=org_data["code"],
                    defaults={
                        "name": org_data["name"],
                        "description": org_data["description"],
                    },
                )
                created_orgs[org_data["code"]] = org
                if created:
                    stats["organizations"] += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"  Created: {org.code} - {org.name}")
                    )
                else:
                    self.stdout.write(f"  Exists: {org.code} - {org.name}")

        # Create offices for each organization
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Creating Offices..."))

        created_offices = {}  # {org_code: {office_code: office}}
        for org_code, offices in OFFICE_STRUCTURES.items():
            created_offices[org_code] = {}
            org = created_orgs[org_code]

            self.stdout.write(f"\n  {org_code}:")

            # First pass: create root offices
            for office_data in offices:
                if office_data["parent"] is None:
                    if dry_run:
                        self.stdout.write(f"    Would create: {office_data['code']} - {office_data['name']}")
                        created_offices[org_code][office_data["code"]] = {"code": office_data["code"]}
                    else:
                        office, created = Office.objects.get_or_create(
                            organization=org,
                            code=office_data["code"],
                            defaults={
                                "name": office_data["name"],
                                "parent": None,
                            },
                        )
                        created_offices[org_code][office_data["code"]] = office
                        if created:
                            stats["offices"] += 1
                            self.stdout.write(
                                self.style.SUCCESS(f"    Created: {office.code} - {office.name}")
                            )
                        else:
                            self.stdout.write(f"    Exists: {office.code} - {office.name}")

            # Second pass: create child offices
            for office_data in offices:
                if office_data["parent"] is not None:
                    parent_office = created_offices[org_code].get(office_data["parent"])

                    if dry_run:
                        self.stdout.write(
                            f"    Would create: {office_data['code']} - {office_data['name']} "
                            f"(under {office_data['parent']})"
                        )
                        created_offices[org_code][office_data["code"]] = {"code": office_data["code"]}
                    else:
                        office, created = Office.objects.get_or_create(
                            organization=org,
                            code=office_data["code"],
                            defaults={
                                "name": office_data["name"],
                                "parent": parent_office,
                            },
                        )
                        created_offices[org_code][office_data["code"]] = office
                        if created:
                            stats["offices"] += 1
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"    Created: {office.code} - {office.name} "
                                    f"(under {parent_office.code})"
                                )
                            )
                        else:
                            self.stdout.write(
                                f"    Exists: {office.code} - {office.name}"
                            )

        # Create users for each office
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Creating Users & Memberships..."))

        used_name_combos = set()

        for org_code, offices in created_offices.items():
            org = created_orgs[org_code]
            self.stdout.write(f"\n  {org_code}:")

            for office_code, office in offices.items():
                self.stdout.write(f"    {office_code}:")

                users_created_for_office = 0
                attempts = 0
                max_attempts = users_per_office * 10  # Prevent infinite loop

                while users_created_for_office < users_per_office and attempts < max_attempts:
                    attempts += 1

                    # Generate unique name
                    first_name = random.choice(FIRST_NAMES)
                    last_name = random.choice(LAST_NAMES)
                    name_key = f"{first_name}_{last_name}_{org_code}"

                    if name_key in used_name_combos:
                        continue

                    used_name_combos.add(name_key)

                    email = self.generate_email(first_name, last_name, org_code, office_code)

                    # First user in office becomes manager
                    is_office_manager = users_created_for_office == 0
                    # First user in first office of org becomes org manager
                    is_org_manager = (
                        users_created_for_office == 0
                        and office_code == list(offices.keys())[0]
                    )

                    if dry_run:
                        role_info = []
                        if is_org_manager:
                            role_info.append("org_manager")
                        if is_office_manager:
                            role_info.append("office_manager")
                        role_str = f" ({', '.join(role_info)})" if role_info else ""
                        self.stdout.write(
                            f"      Would create: {first_name} {last_name} <{email}>{role_str}"
                        )
                    else:
                        # Check if user already exists
                        user = User.objects.filter(email=email).first()
                        if not user:
                            user = User.objects.create_user(
                                email=email,
                                password=password,
                                first_name=first_name,
                                last_name=last_name,
                            )
                            stats["users"] += 1

                        # Create organization membership
                        org_membership, created = OrganizationMembership.objects.get_or_create(
                            user=user,
                            organization=org,
                            defaults={
                                "role": "org_manager" if is_org_manager else "org_member",
                                "status": "approved",
                            },
                        )
                        if created:
                            stats["org_memberships"] += 1

                        # Create office membership
                        office_membership, created = OfficeMembership.objects.get_or_create(
                            user=user,
                            office=office,
                            defaults={
                                "role": "manager" if is_office_manager else "member",
                            },
                        )
                        if created:
                            stats["office_memberships"] += 1

                        role_info = []
                        if is_org_manager:
                            role_info.append("org_manager")
                        if is_office_manager:
                            role_info.append("office_manager")
                        role_str = f" ({', '.join(role_info)})" if role_info else ""

                        self.stdout.write(
                            self.style.SUCCESS(
                                f"      Created: {user.full_name} <{user.email}>{role_str}"
                            )
                        )

                    users_created_for_office += 1

        # Print summary
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Summary"))
        self.stdout.write("-" * 50)

        if dry_run:
            total_orgs = len(ORGANIZATIONS)
            total_offices = sum(len(offices) for offices in OFFICE_STRUCTURES.values())
            total_users = total_offices * users_per_office

            self.stdout.write(f"Would create:")
            self.stdout.write(f"  Organizations:      {total_orgs}")
            self.stdout.write(f"  Offices:            {total_offices}")
            self.stdout.write(f"  Users:              {total_users}")
            self.stdout.write(f"  Org Memberships:    {total_users}")
            self.stdout.write(f"  Office Memberships: {total_users}")
        else:
            self.stdout.write(f"Created:")
            self.stdout.write(f"  Organizations:      {stats['organizations']}")
            self.stdout.write(f"  Offices:            {stats['offices']}")
            self.stdout.write(f"  Users:              {stats['users']}")
            self.stdout.write(f"  Org Memberships:    {stats['org_memberships']}")
            self.stdout.write(f"  Office Memberships: {stats['office_memberships']}")

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"All users have password: {password}"
            )
        )
        self.stdout.write("")

        # Show sample login info
        if not dry_run and stats["users"] > 0:
            self.stdout.write(self.style.MIGRATE_HEADING("Sample Login Credentials"))
            self.stdout.write("-" * 50)
            sample_users = User.objects.filter(
                email__endswith="@acme.com"
            ).order_by("id")[:3]
            for user in sample_users:
                self.stdout.write(f"  Email: {user.email}")
                self.stdout.write(f"  Password: {password}")
                self.stdout.write("")
