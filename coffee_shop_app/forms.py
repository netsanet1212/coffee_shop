import re

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import User


class SignInForm(AuthenticationForm):
    # The field is still called "username" internally, but holds the email.
    username = forms.EmailField(label="Email Address")

    error_messages = {
        "invalid_login": "Incorrect email or password.",
        "inactive": "This account is inactive.",
    }


class SignUpForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("first_name", "last_name", "email", "phone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("first_name", "last_name", "phone"):
            self.fields[name].required = True

    def clean_phone(self):
        digits = re.sub(r"[\s\-()+]", "", self.cleaned_data["phone"])
        if not re.fullmatch(r"\d{9,15}", digits):
            raise forms.ValidationError("Enter a valid phone number.")
        return digits
