from django import forms
from django.db import models
from django.utils import timezone
from .models import Animal, Species, TrackingTag, Deployment, Geofence


class AnimalForm(forms.ModelForm):
    """Form for adding/editing animals with species choices and ESP32 tag attachment."""

    SPECIES_CHOICES = [
        ('', '-- Select Species --'),
        ('Lion', 'Lion (Panthera leo)'),
        ('Elephant', 'African Elephant (Loxodonta africana)'),
        ('Giraffe', 'Giraffe (Giraffa camelopardalis)'),
        ('Zebra', 'Plains Zebra (Equus quagga)'),
    ]

    species_name = forms.ChoiceField(
        choices=SPECIES_CHOICES,
        label='Species',
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    GENDER_CHOICES = [
        ('', '-- Select Gender --'),
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Unknown', 'Unknown'),
    ]

    gender = forms.ChoiceField(
        choices=GENDER_CHOICES,
        label='Gender',
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    esp32_tag = forms.ModelChoiceField(
        queryset=TrackingTag.objects.none(),
        required=False,
        label='Attach ESP32 Tag',
        empty_label='-- No Tag (Select Later) --',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Animal
        fields = ['nickname', 'gender', 'birth_year', 'weight', 'health_status', 'notes']
        widgets = {
            'nickname': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter animal nickname'}),
            'birth_year': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 2018'}),
            'weight': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Weight in kg', 'step': '0.01'}),
            'health_status': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Healthy, Injured, Sick'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Additional notes...', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        try:
            self.fields['esp32_tag'].queryset = TrackingTag.objects.filter(is_assigned=False)

            if self.instance and self.instance.pk:
                if hasattr(self.instance, 'species') and self.instance.species:
                    self.fields['species_name'].initial = self.instance.species.common_name

                current_tag_id = None
                try:
                    deployment = self.instance.deployment_set.filter(is_active=True).first()
                    if deployment and deployment.tag:
                        current_tag_id = deployment.tag_id
                        self.fields['esp32_tag'].initial = deployment.tag
                except Exception:
                    pass

                if current_tag_id:
                    self.fields['esp32_tag'].queryset = TrackingTag.objects.filter(
                        models.Q(is_assigned=False) | models.Q(tag_id=current_tag_id)
                    )
                else:
                    self.fields['esp32_tag'].queryset = TrackingTag.objects.filter(is_assigned=False)
        except Exception:
            pass

    def clean(self):
        cleaned_data = super().clean()
        species_name = cleaned_data.get('species_name')
        if species_name:
            valid_species = [choice[0] for choice in self.SPECIES_CHOICES if choice[0]]
            if species_name not in valid_species:
                self.add_error('species_name', 'Please select a valid species.')
        return cleaned_data

    def save(self, commit=True):
        species_name = self.cleaned_data.get('species_name')
        esp32_tag = self.cleaned_data.get('esp32_tag')

        species_map = {
            'Lion': 'Panthera leo',
            'Elephant': 'Loxodonta africana',
            'Giraffe': 'Giraffa camelopardalis',
            'Zebra': 'Equus quagga',
        }

        if species_name:
            species_obj, created = Species.objects.get_or_create(
                common_name=species_name,
                defaults={'scientific_name': species_map.get(species_name, 'Unknown')}
            )
            self.instance.species = species_obj

        instance = super().save(commit=commit)

        if esp32_tag:
            existing = Deployment.objects.filter(animal=instance, tag=esp32_tag, is_active=True).first()
            if not existing:
                Deployment.objects.filter(tag=esp32_tag, is_active=True).exclude(animal=instance).update(
                    is_active=False,
                    end_date=timezone.now()
                )

                old_deployments = Deployment.objects.filter(animal=instance, is_active=True).exclude(tag=esp32_tag)
                for dep in old_deployments:
                    dep.is_active = False
                    dep.end_date = timezone.now()
                    dep.save()
                    if dep.tag:
                        dep.tag.is_assigned = False
                        dep.tag.save()

                Deployment.objects.create(animal=instance, tag=esp32_tag, is_active=True)
                esp32_tag.is_assigned = True
                esp32_tag.save()
        else:
            old_deployments = Deployment.objects.filter(animal=instance, is_active=True)
            for dep in old_deployments:
                dep.is_active = False
                dep.end_date = timezone.now()
                dep.save()
                if dep.tag:
                    dep.tag.is_assigned = False
                    dep.tag.save()

        return instance


class TrackingTagForm(forms.ModelForm):
    """Form for adding/editing tracking tags."""

    class Meta:
        model = TrackingTag
        fields = ['tag_serial_number', 'model', 'manufacturer', 'battery_level', 'last_service_date']
        widgets = {
            'tag_serial_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., ESP32-TAG-001 or TAG-2024-001'
            }),
            'model': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., ESP32-GPS, Garmin, Telonics'
            }),
            'manufacturer': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., ESP32, Garmin, Telonics'
            }),
            'battery_level': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Battery percentage (0-100)',
                'min': '0',
                'max': '100',
                'step': '0.01'
            }),
            'last_service_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
        }


class GeofenceForm(forms.ModelForm):
    """Form for adding/editing geofences."""

    class Meta:
        model = Geofence
        fields = ['name', 'center_latitude', 'center_longitude', 'radius_meters']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Northern Reserve Boundary'
            }),
            'center_latitude': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., -0.4167',
                'step': '0.00000001'
            }),
            'center_longitude': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 36.9500',
                'step': '0.00000001'
            }),
            'radius_meters': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Radius in meters (e.g., 500)',
                'min': '1',
                'step': '1'
            }),
        }