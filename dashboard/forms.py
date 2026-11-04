from django import forms
from django.contrib.auth import get_user_model
from django.core.validators import validate_email

from .models import Profile, ScheduledReport


class ProfileForm(forms.ModelForm):
    job_title = forms.CharField(max_length=80, required=False)

    class Meta:
        model = get_user_model()
        fields = ["first_name", "last_name", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["job_title"].initial = self.instance.profile.job_title
        self.fields["email"].required = True

    def save(self, commit=True):
        user = super().save(commit)
        user.profile.job_title = self.cleaned_data["job_title"]
        user.profile.save(update_fields=["job_title"])
        return user


class PreferencesForm(forms.ModelForm):
    timezone = forms.ChoiceField(choices=[(t, t.replace("_", " ")) for t in Profile.TIMEZONES])

    class Meta:
        model = Profile
        fields = ["currency", "timezone", "accent"]
        widgets = {"accent": forms.RadioSelect}


class ScheduledReportForm(forms.ModelForm):
    class Meta:
        model = ScheduledReport
        fields = ["name", "frequency", "format", "recipients"]
        widgets = {"recipients": forms.TextInput(attrs={"placeholder": "ceo@example.com, team@example.com"})}

    def clean_recipients(self):
        emails = [e.strip() for e in self.cleaned_data["recipients"].split(",") if e.strip()]
        if not emails:
            raise forms.ValidationError("Add at least one e-mail address.")
        if len(emails) > 10:
            raise forms.ValidationError("Up to 10 recipients.")
        for e in emails:
            validate_email(e)
        return ", ".join(emails)
