"""Forms for triggering new analyses."""

from __future__ import annotations

from django import forms


PROVIDER_CHOICES = [
    ("ollama", "Ollama (local)"),
    ("bedrock", "AWS Bedrock"),
]


class AnalysisForm(forms.Form):
    repo_path = forms.CharField(
        label="Repository path",
        max_length=500,
        widget=forms.TextInput(attrs={"placeholder": "/path/to/repo", "class": "form-control"}),
    )
    commit = forms.CharField(
        label="Commit ref",
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "HEAD, abc123, v1.2.0 …", "class": "form-control"}
        ),
    )
    from_ref = forms.CharField(
        label="From ref (range start)",
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "e.g. main~5", "class": "form-control"}
        ),
    )
    to_ref = forms.CharField(
        label="To ref (range end)",
        max_length=255,
        required=False,
        initial="HEAD",
        widget=forms.TextInput(attrs={"placeholder": "HEAD", "class": "form-control"}),
    )
    provider = forms.ChoiceField(
        label="AI provider",
        choices=PROVIDER_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def clean(self) -> dict:
        cleaned = super().clean()
        commit = cleaned.get("commit")
        from_ref = cleaned.get("from_ref")

        if commit and from_ref:
            raise forms.ValidationError(
                "Specify either a Commit ref or a From/To range — not both."
            )
        if not commit and not from_ref:
            cleaned["commit"] = "HEAD"

        return cleaned
