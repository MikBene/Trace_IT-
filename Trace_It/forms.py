from django import forms
from .models import Animal, Species, TrackingTag, Geofence


class AnimalForm(forms.ModelForm):
    """Form for adding/editing animals with 4 default species choices."""

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

    class Meta:
        model = Animal
        fields = ['nickname', 'species_name', 'gender', 'birth_year', 'weight', 'health_status', 'photo']
        widgets = {
            'nickname': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter animal nickname'}),
            'birth_year': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 2018'}),
            'weight': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Weight in kg', 'step': '0.01'}),
            'health_status': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Healthy, Injured, Sick'}),
            'photo': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def save(self, commit=True):
        species_name = self.cleaned_data.pop('species_name')
        instance = super().save(commit=False)

        species_map = {
            'Lion': 'Panthera leo',
            'Elephant': 'Loxodonta africana',
            'Giraffe': 'Giraffa camelopardalis',
            'Zebra': 'Equus quagga',
        }

        species_obj, created = Species.objects.get_or_create(
            common_name=species_name,
            defaults={'scientific_name': species_map.get(species_name, 'Unknown')}
        )
        instance.species = species_obj

        if commit:
            instance.save()
        return instance


class TrackingTagForm(forms.ModelForm):
    """Form for adding/editing tracking tags."""

    class Meta:
        model = TrackingTag
        fields = ['tag_serial_number', 'battery_level', 'manufacturer', 'last_service_date']
        widgets = {
            'tag_serial_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., TAG-2024-001'
            }),
            'battery_level': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Battery percentage (0-100)',
                'min': '0',
                'max': '100',
                'step': '0.01'
            }),
            'manufacturer': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Garmin, Telonics'
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