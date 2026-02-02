"""Migration to simplify the permission model.

Changes:
- Office: Remove permissions JSONField, change related_name sub_offices to children
- OfficeMembership: Simplify roles to admin/member, remove status field, immediate membership
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('organizations', '0001_initial'),
    ]

    operations = [
        # 1. FIRST: Migrate role data (while old field names exist)
        # This uses raw SQL to avoid model ordering issues
        migrations.RunSQL(
            # Forward: Map old roles to new roles
            """
            UPDATE organizations_officemembership
            SET role = CASE
                WHEN role = 'manager' THEN 'admin'
                WHEN role = 'reviewer' THEN 'member'
                WHEN role = 'viewer' THEN 'member'
                ELSE 'member'
            END;
            """,
            # Reverse: Set all back to reviewer
            """
            UPDATE organizations_officemembership SET role = 'reviewer';
            """,
        ),

        # Office model changes
        # 2. Remove permissions field
        migrations.RemoveField(
            model_name='office',
            name='permissions',
        ),

        # 3. Add index on parent field
        migrations.AddIndex(
            model_name='office',
            index=models.Index(fields=['parent'], name='organizatio_parent__9ac4b4_idx'),
        ),

        # OfficeMembership model changes
        # IMPORTANT: Remove index BEFORE removing the status field (SQLite limitation)
        # 4. Remove status index
        migrations.RemoveIndex(
            model_name='officemembership',
            name='organizatio_status_11f77d_idx',
        ),

        # 5. Remove status field
        migrations.RemoveField(
            model_name='officemembership',
            name='status',
        ),

        # 6. Remove reviewed_at field
        migrations.RemoveField(
            model_name='officemembership',
            name='reviewed_at',
        ),

        # 7. Remove rejection_reason field
        migrations.RemoveField(
            model_name='officemembership',
            name='rejection_reason',
        ),

        # 8. Rename requested_at to joined_at
        migrations.RenameField(
            model_name='officemembership',
            old_name='requested_at',
            new_name='joined_at',
        ),

        # 9. Rename reviewed_by to added_by
        migrations.RenameField(
            model_name='officemembership',
            old_name='reviewed_by',
            new_name='added_by',
        ),

        # 10. Update added_by related_name
        migrations.AlterField(
            model_name='officemembership',
            name='added_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='office_memberships_added',
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # 11. Change role field choices and default
        migrations.AlterField(
            model_name='officemembership',
            name='role',
            field=models.CharField(
                choices=[('admin', 'Admin'), ('member', 'Member')],
                default='member',
                max_length=20,
            ),
        ),

        # 12. Add new index on role
        migrations.AddIndex(
            model_name='officemembership',
            index=models.Index(fields=['role'], name='organizatio_role_7c0254_idx'),
        ),
    ]
