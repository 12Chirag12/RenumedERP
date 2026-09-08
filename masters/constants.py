"""
masters/constants.py

get_departments() now queries MstDepartment from MySQL.
This is the ONLY file that changed when moving from hardcoded list → DB.
No other file needed updating.
"""

def get_departments():
    """
    Returns all departments from MstDepartment table.
    Imported lazily to avoid app-registry issues at startup.
    """
    from .models import MstDepartment
    return MstDepartment.objects.all()