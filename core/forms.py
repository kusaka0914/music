from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from .models import Profile, MusicPost, Comment, Playlist, MusicTaste, MusicStory
import json

class UserLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'ユーザー名',
            'autocomplete': 'username'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'パスワード',
            'autocomplete': 'current-password'
        })
    )

class UserRegisterForm(UserCreationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'ユーザー名（半角英数字）',
            'autocomplete': 'username'
        })
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'メールアドレス',
            'autocomplete': 'email'
        })
    )
    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'パスワード',
            'autocomplete': 'new-password'
        })
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'パスワード（確認）',
            'autocomplete': 'new-password'
        })
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # パスワードのヘルプテキストをカスタマイズ
        self.fields['password1'].help_text = '8文字以上で、文字と数字を含める必要があります'
        self.fields['password2'].help_text = '確認のため、同じパスワードを入力してください'
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
        fields = ['title', 'artist', 'spotify_link', 'description', 'mood']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'artist': forms.TextInput(attrs={'class': 'form-control'}),
            'spotify_link': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'mood': forms.Select(attrs={'class': 'form-control'}),
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
    class Meta:
        model = MusicTaste
        fields = ['genres', 'moods', 'favorite_artists']
        widgets = {
            'genres': forms.TextInput(attrs={'class': 'form-control', 'type': 'hidden'}),
            'moods': forms.TextInput(attrs={'class': 'form-control', 'type': 'hidden'}),
            'favorite_artists': forms.TextInput(attrs={'class': 'form-control', 'type': 'hidden'})
        }

    def clean_genres(self):
        genres = self.cleaned_data.get('genres')
        if isinstance(genres, str):
            try:
                genres = json.loads(genres)
            except json.JSONDecodeError:
                genres = []
        if not isinstance(genres, list):
            genres = []
        return genres

    def clean_moods(self):
        moods = self.cleaned_data.get('moods')
        if isinstance(moods, str):
            try:
                moods = json.loads(moods)
            except json.JSONDecodeError:
                moods = []
        if not isinstance(moods, list):
            moods = []
        return moods

    def clean_favorite_artists(self):
        artists = self.cleaned_data.get('favorite_artists')
        if isinstance(artists, str):
            try:
                artists = json.loads(artists)
            except json.JSONDecodeError:
                artists = []
        if not isinstance(artists, list):
            artists = []
        return artists

class ProfileEditForm(forms.ModelForm):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'ユーザー名を入力（半角英数字）'
        })
    )
    nickname = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'ニックネームを入力'
        })
    )
    bio = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': '自己紹介を入力（500文字まで）',
            'rows': 4
        })
    )
    website = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            'class': 'form-control',
            'placeholder': 'https://example.com'
        })
    )
    avatar = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*'
        })
    )

    class Meta:
        model = Profile
        fields = ['avatar', 'nickname', 'bio', 'website']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['username'].initial = user.username
            self.fields['nickname'].initial = user.profile.nickname

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if not username.isascii():
            raise forms.ValidationError('ユーザー名は半角英数字で入力してください。')
        if ' ' in username:
            raise forms.ValidationError('ユーザー名にスペースは使用できません。')
        if User.objects.exclude(pk=self.instance.user.pk).filter(username=username).exists():
            raise forms.ValidationError('このユーザー名は既に使用されています。')
        return username

    def save(self, commit=True):
        profile = super().save(commit=False)
        if commit:
            profile.user.username = self.cleaned_data['username']
            profile.user.save()
            profile.nickname = self.cleaned_data['nickname']
            profile.save()
        return profile 

class MusicStoryForm(forms.ModelForm):
    class Meta:
        model = MusicStory
        fields = ['spotify_track_id', 'mood', 'comment', 'background_theme', 'listening_status']
        widgets = {
            'comment': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'maxlength': 200,
                'placeholder': 'コメントを追加...'
            }),
            'mood': forms.Select(attrs={'class': 'form-control'}),
            'background_theme': forms.Select(attrs={'class': 'form-control'}),
            'listening_status': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean_comment(self):
        comment = self.cleaned_data.get('comment')
        if comment and len(comment) > 200:
            raise forms.ValidationError('コメントは200文字以内で入力してください。')
        return comment 
    
    def clean_spotify_track_id(self):
        spotify_track_id = self.cleaned_data.get('spotify_track_id')
        if not spotify_track_id:
            raise forms.ValidationError('SpotifyトラックIDを入力してください。')
        return spotify_track_id

