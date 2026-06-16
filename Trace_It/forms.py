from django import forms
from django.db import models
from django.utils import timezone
from .models import Animal, Species, TrackingTag, Geofence, Deployment


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

    # ESP32 Tag selection - only show unassigned tags
    esp32_tag = forms.ModelChoiceField(
        queryset=TrackingTag.objects.filter(is_assigned=False),
        required=False,
        label='Attach ESP32 Tag',
        empty_label='-- No Tag (Select Later) --',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Animal
        fields = ['nickname', 'species_name', 'gender', 'birth_year', 'weight', 'health_status', 'photo', 'esp32_tag']
        widgets = {
            'nickname': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter animal nickname'}),
            'birth_year': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 2018'}),
            'weight': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Weight in kg', 'step': '0.01'}),
            'health_status': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Healthy, Injured, Sick'}),
            'photo': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # If editing, include the currently assigned tag in the queryset
        if self.instance and self.instance.pk:
            current_tag_id = None
            deployment = self.instance.deployment_set.filter(is_active=True).first()
            if deployment:
                current_tag_id = deployment.tag_id
                self.fields['esp32_tag'].initial = deployment.tag
            self.fields['esp32_tag'].queryset = TrackingTag.objects.filter(
                models.Q(is_assigned=False) | models.Q(tag_id=current_tag_id)
            ) if current_tag_id else TrackingTag.objects.filter(is_assigned=False)

    def save(self, commit=True):
        # Get values BEFORE calling super save
        species_name = self.cleaned_data.get('species_name')
        esp32_tag = self.cleaned_data.get('esp32_tag')
        
        # Create species object
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
        
        # Set species on instance
        self.instance.species = species_obj
        
        # Save the animal (auto-generates animal_id)
        instance = super().save(commit=commit)
        
        # Handle ESP32 tag assignment
        if esp32_tag:
            # End any existing active deployment for this tag
            Deployment.objects.filter(tag=esp32_tag, is_active=True).update(
                is_active=False, 
                end_date=timezone.now()
            )
            
            # End any existing active deployment for this animal
            Deployment.objects.filter(animal=instance, is_active=True).update(
                is_active=False,
                end_date=timezone.now()
            )
            
            # Create new deployment linking animal to tag
            Deployment.objects.create(
                animal=instance,
                tag=esp32_tag,
                is_active=True
            )
            
            # Mark tag as assigned
            esp32_tag.is_assigned = True
            esp32_tag.save()

        return instance


class TrackingTagForm(forms.ModelForm):
    """Form for adding/editing tracking tags."""

    class Meta:
        model = TrackingTag
        fields = ['tag_serial_number', 'battery_level', 'manufacturer', 'last_service_date']
        widgets = {
            'tag_serial_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., ESP32-TAG-001 or TAG-2024-001'
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
                'placeholder': 'e.g., ESP32, Garmin, Telonics'
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