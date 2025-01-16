from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField(max_length=500, blank=True)
    followers = models.ManyToManyField(User, related_name='following', blank=True)
    favorite_genres = models.JSONField(default=dict, blank=True)
    favorite_artists = models.JSONField(default=dict, blank=True)
    music_mood_preferences = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f'{self.user.username}のプロフィール'

    def get_music_compatibility(self, other_profile):
        """他のユーザーとの音楽の相性を計算"""
        compatibility_score = 0
        
        # ジャンルの比較
        my_genres = set(self.favorite_genres.get('genres', []))
        other_genres = set(other_profile.favorite_genres.get('genres', []))
        genre_match = len(my_genres & other_genres)
        compatibility_score += genre_match * 2
        
        # アーティストの比較
        my_artists = set(self.favorite_artists.get('artists', []))
        other_artists = set(other_profile.favorite_artists.get('artists', []))
        artist_match = len(my_artists & other_artists)
        compatibility_score += artist_match * 3
        
        # ムードの比較
        my_moods = set(self.music_mood_preferences.get('moods', []))
        other_moods = set(other_profile.music_mood_preferences.get('moods', []))
        mood_match = len(my_moods & other_moods)
        compatibility_score += mood_match
        
        # 最大スコアで正規化（0-100の範囲に）
        max_score = (len(my_genres) + len(other_genres)) * 2 + \
                   (len(my_artists) + len(other_artists)) * 3 + \
                   (len(my_moods) + len(other_moods))
        
        if max_score == 0:
            return 0
            
        normalized_score = (compatibility_score / max_score) * 100
        return round(normalized_score, 2)

    def get_music_compatibility_with_user(self, other_user):
        """他のユーザーとの音楽の相性を計算"""
        compatibility_score = 0
        
        # 1. ジャンルの比較 (重み: 2点/マッチ)
        my_genres = set(self.favorite_genres.get('genres', []))
        other_genres = set(other_user.profile.favorite_genres.get('genres', []))
        genre_match = len(my_genres & other_genres)
        compatibility_score += genre_match * 2
        
        # 2. アーティストの比較 (重み: 3点/マッチ)
        my_artists = set(self.favorite_artists.get('artists', []))
        other_artists = set(other_user.profile.favorite_artists.get('artists', []))
        artist_match = len(my_artists & other_artists)
        compatibility_score += artist_match * 3
        
        # 3. ムード（曲調）の比較 (重み: 1点/マッチ)
        my_moods = set(self.music_mood_preferences.get('moods', []))
        other_moods = set(other_user.profile.music_mood_preferences.get('moods', []))
        mood_match = len(my_moods & other_moods)
        compatibility_score += mood_match
        
        # 4. スコアの正規化（0-100%）
        max_score = (len(my_genres) + len(other_genres)) * 2 + \
                   (len(my_artists) + len(other_artists)) * 3 + \
                   (len(my_moods) + len(other_moods))
        
        if max_score == 0:
            return 0
            
        normalized_score = (compatibility_score / max_score) * 100
        return round(normalized_score, 2)

class MusicPost(models.Model):
    MOOD_CHOICES = [
        ('morning', '朝'),
        ('night', '夜'),
        ('rain', '雨の日'),
        ('drive', 'ドライブ'),
        ('work', '作業'),
        ('relax', 'リラックス'),
        ('party', 'パーティー'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    artist = models.CharField(max_length=100)
    spotify_link = models.CharField(max_length=200)
    youtube_link = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    likes = models.ManyToManyField(User, related_name='liked_posts', blank=True)
    
    # 新しいフィールド
    mood = models.CharField(max_length=20, choices=MOOD_CHOICES, blank=True)
    scheduled_time = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    image = models.ImageField(upload_to='post_images/', blank=True, null=True)
    
    def __str__(self):
        return f'{self.title} - {self.artist}'

    class Meta:
        ordering = ['-created_at']

class Comment(models.Model):
    post = models.ForeignKey(MusicPost, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.username}のコメント on {self.post.title}'

class Playlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    posts = models.ManyToManyField(MusicPost, related_name='playlists', blank=True)
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username}の{self.title}'

class Notification(models.Model):
    LIKE = 'like'
    COMMENT = 'comment'
    FOLLOW = 'follow'
    NOTIFICATION_TYPES = [
        (LIKE, 'いいね'),
        (COMMENT, 'コメント'),
        (FOLLOW, 'フォロー'),
    ]

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications_received')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications_sent')
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    post = models.ForeignKey(MusicPost, on_delete=models.CASCADE, null=True, blank=True)
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.sender.username}から{self.recipient.username}への{self.get_notification_type_display()}'

    class Meta:
        ordering = ['-created_at']

class MusicTaste(models.Model):
    GENRE_CHOICES = [
        ('pop', 'ポップ'),
        ('rock', 'ロック'),
        ('jazz', 'ジャズ'),
        ('classical', 'クラシック'),
        ('hiphop', 'ヒップホップ'),
        ('electronic', 'エレクトロニック'),
        ('rnb', 'R&B'),
        ('metal', 'メタル'),
        ('folk', 'フォーク'),
        ('indie', 'インディー'),
    ]

    MOOD_CHOICES = [
        ('energetic', '元気'),
        ('calm', '穏やか'),
        ('melancholic', '物悲しい'),
        ('romantic', 'ロマンティック'),
        ('angry', '激しい'),
        ('happy', '明るい'),
        ('sad', '悲しい'),
        ('nostalgic', 'ノスタルジック'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='music_taste')
    genres = models.JSONField(default=dict)  # 好きなジャンルとその強度
    moods = models.JSONField(default=dict)   # 好きな曲調とその強度
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username}の音楽の好み'

    @property
    def top_genres(self):
        """最も好きなジャンルを強度順に取得"""
        genres = self.genres.get('preferences', {})
        return dict(sorted(genres.items(), key=lambda x: x[1], reverse=True)[:5])

    @property
    def top_moods(self):
        """最も好きな曲調を強度順に取得"""
        moods = self.moods.get('preferences', {})
        return dict(sorted(moods.items(), key=lambda x: x[1], reverse=True)[:5])

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
        MusicTaste.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()
    if hasattr(instance, 'music_taste'):
        instance.music_taste.save()
