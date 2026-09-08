"""
users/forms.py

Forms used in the Users app:
  - LoginForm           : Username + password for login page
  - CreateUserForm      : Admin-only form to create new users
  - ChangePasswordForm  : Used when user must change their password
"""

from django import forms
from django.contrib.auth.models import Group, User

from .access import get_department_groups, get_role_groups
from .models import UserProfile


class LoginForm(forms.Form):
    """Simple login form with username and password."""

    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter your username',
            'class': 'form-input',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Enter your password',
            'class': 'form-input',
        })
    )


class CreateUserForm(forms.ModelForm):
    """
    Form for Admin to create a new user.
    Includes cascading department → sub-department → role selection
    and a temporary password.
    The department/sub_department/role dropdowns are populated
    and validated client-side via JavaScript; the values arrive
    as plain strings in POST data.
    """

    password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Minimum 8 characters',
            'class': 'form-input',
        }),
        help_text='User will be asked to change this on first login.'
    )

    department = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-input'}),
    )

    sub_department = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-input'}),
    )

    role = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-input'}),
    )

    role_group = forms.ModelChoiceField(
        queryset=Group.objects.none(),
        required=False,
        label='Role-based access group',
        empty_label='— Select role group (optional) —',
    )

    department_group = forms.ModelChoiceField(
        queryset=Group.objects.none(),
        required=False,
        label='Department-based access group',
        empty_label='— Select department group (optional) —',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role_group'].queryset = get_role_groups()
        self.fields['department_group'].queryset = get_department_groups()

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'First name'}),
            'last_name':  forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Last name'}),
            'username':   forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Login username'}),
        }

    def clean_username(self):
        """Make sure the username isn't already taken."""
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('This username is already taken.')
        return username


class ChangePasswordForm(forms.Form):
    """Form for users to set a new password (used on first login or from settings)."""

    new_password = forms.CharField(
        min_length=8,
        label='New Password',
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Enter new password (min 8 characters)',
            'class': 'form-input',
        })
    )
    confirm_password = forms.CharField(
        label='Confirm New Password',
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Re-enter new password',
            'class': 'form-input',
        })
    )

    def clean(self):
        """Ensure both password fields match."""
        cleaned_data = super().clean()
        p1 = cleaned_data.get('new_password')
        p2 = cleaned_data.get('confirm_password')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Passwords do not match. Please try again.')
        return cleaned_data
