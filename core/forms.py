from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Profile, MusicPost, Comment, Playlist, MusicTaste

class UserRegisterForm(UserCreationForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

class UserUpdateForm(forms.ModelForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ['username', 'email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['bio']
        widgets = {
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

class MusicPostForm(forms.ModelForm):
    class Meta:
        model = MusicPost
        fields = ['title', 'artist', 'spotify_link', 'description', 'mood', 'scheduled_time', 'location', 'image']
        widgets = {
            'scheduled_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'mood': forms.Select(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'placeholder': '場所（任意）'}),
        }

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'コメントを入力してください...'
            }),
        }

class PlaylistForm(forms.ModelForm):
    class Meta:
        model = Playlist
        fields = ['title', 'description', 'is_public']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class MusicTasteForm(forms.ModelForm):
    genres = forms.MultipleChoiceField(
        choices=MusicTaste.GENRE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
    moods = forms.MultipleChoiceField(
        choices=MusicTaste.MOOD_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
    favorite_artists = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='アーティスト名をカンマ区切りで入力してください',
        required=False
    )

    class Meta:
        model = MusicTaste
        fields = ['genres', 'moods']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get('instance')
        if instance:
            self.fields['genres'].initial = [k for k, v in instance.genres.get('preferences', {}).items() if v > 0]
            self.fields['moods'].initial = [k for k, v in instance.moods.get('preferences', {}).items() if v > 0]
            self.fields['favorite_artists'].initial = ', '.join(
                instance.user.profile.favorite_artists.get('artists', [])
            )

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # ジャンルの保存
        genres_dict = {genre: 1 for genre in self.cleaned_data['genres']}
        instance.genres = {'preferences': genres_dict}
        
        # ムードの保存
        moods_dict = {mood: 1 for mood in self.cleaned_data['moods']}
        instance.moods = {'preferences': moods_dict}
        
        if commit:
            instance.save()
            
            # お気に入りアーティストの保存
            artists = [
                artist.strip()
                for artist in self.cleaned_data['favorite_artists'].split(',')
                if artist.strip()
            ]
            instance.user.profile.favorite_artists = {'artists': artists}
            instance.user.profile.save()
            
        return instance 