"""Utility functions for package file handling."""

import hashlib


def calculate_file_hash(file_obj):
    """Calculate SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    file_obj.seek(0)
    for chunk in file_obj.chunks() if hasattr(file_obj, 'chunks') else iter(lambda: file_obj.read(8192), b''):
        sha256.update(chunk)
    file_obj.seek(0)
    return sha256.hexdigest()


def get_upload_path(instance, filename):
    """Generate upload path for documents."""
    tab = instance.tab
    package = tab.package
    org_code = package.organization.code.lower()
    return f"packages/{org_code}/{package.reference_number}/{tab.identifier}/v{instance.version}_{filename}"
