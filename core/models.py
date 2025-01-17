import logging
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q

logger = logging.getLogger(__name__)


from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField(max_length=500, blank=True)
    website = models.URLField(max_length=200, blank=True)
    avatar = models.ImageField(upload_to='profile_pics', default='default.jpg')
    spotify_refresh_token = models.CharField(max_length=200, blank=True, null=True)
    favorite_genres = models.JSONField(default=list, blank=True)
    favorite_artists = models.JSONField(default=list, blank=True)
    music_mood_preferences = models.JSONField(default=dict, blank=True)
    nickname = models.CharField(max_length=50, blank=True)
    following = models.ManyToManyField('self', symmetrical=False, related_name='followed_by', blank=True)

    def __str__(self):
        return f'{self.user.username} Profile'

    @property
    def spotify_connected(self):
        return bool(self.spotify_refresh_token)

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

    def get_common_music_interests(self, other_user):
        """他のユーザーとの共通の音楽趣味を取得"""
        try:
            my_taste = self.user.music_taste
            other_taste = other_user.music_taste

            # 共通のジャンル
            my_genres = set(my_taste.genres.get('preferences', {}).keys())
            other_genres = set(other_taste.genres.get('preferences', {}).keys())
            common_genres = my_genres & other_genres

            # 共通のアーティスト
            my_artists = set(artist['name'] for artist in my_taste.favorite_artists)
            other_artists = set(artist['name'] for artist in other_taste.favorite_artists)
            common_artists = my_artists & other_artists

            return {
                'genres': list(common_genres),
                'artists': list(common_artists)
            }
        except Exception as e:
            logger.error(f"共通の音楽趣味の取得に失敗: {str(e)}")
            return {'genres': [], 'artists': []}

    def get_music_compatibility_score(self, other_user):
        """他のユーザーとの音楽の相性スコアを計算（0-100）"""
        try:
            common = self.get_common_music_interests(other_user)
            my_taste = self.user.music_taste
            other_taste = other_user.music_taste

            # ジャンルとアーティストの総数を取得
            total_genres = len(set(my_taste.genres.get('preferences', {}).keys()) | 
                             set(other_taste.genres.get('preferences', {}).keys()))
            total_artists = len(set(artist['name'] for artist in my_taste.favorite_artists) | 
                              set(artist['name'] for artist in other_taste.favorite_artists))

            # 共通の要素の数を取得
            common_genres = len(common['genres'])
            common_artists = len(common['artists'])

            # スコアを計算（ジャンルとアーティストで50点ずつ）
            genre_score = (common_genres / total_genres * 50) if total_genres > 0 else 0
            artist_score = (common_artists / total_artists * 50) if total_artists > 0 else 0

            return round(genre_score + artist_score)
        except Exception as e:
            logger.error(f"音楽の相性スコアの計算に失敗: {str(e)}")
            return 0

    def get_achievement_badges(self):
        """ユーザーの獲得バッジを取得"""
        badges = []
        
        # 投稿数に応じたバッジ
        post_count = self.user.musicpost_set.count()
        if post_count >= 100:
            badges.append({
                'name': '音楽マエストロ',
                'description': '100件以上の投稿を達成',
                'icon': '🎵'
            })
        elif post_count >= 50:
            badges.append({
                'name': '熱心な共有者',
                'description': '50件以上の投稿を達成',
                'icon': '🎼'
            })
        elif post_count >= 10:
            badges.append({
                'name': '音楽の語り手',
                'description': '10件以上の投稿を達成',
                'icon': '🎧'
            })

        # ジャンルの多様性に応じたバッジ
        try:
            genre_count = len(self.user.music_taste.genres.get('preferences', {}))
            if genre_count >= 10:
                badges.append({
                    'name': 'ジャンルマスター',
                    'description': '10種類以上のジャンルを探求',
                    'icon': '🌈'
                })
            elif genre_count >= 5:
                badges.append({
                    'name': '音楽の探検家',
                    'description': '5種類以上のジャンルを探求',
                    'icon': '🔍'
                })
        except:
            pass

        # Spotify連携バッジ
        if self.spotify_connected:
            badges.append({
                'name': 'Spotify達人',
                'description': 'Spotifyと連携してプレイリストを共有',
                'icon': '🎯'
            })

        return badges

    def get_recommended_users(self, limit=5):
        """おすすめユーザーを取得"""
        try:
            # 自分がフォローしているユーザーを取得
            following_users = self.following.all()
            
            # フォローしているユーザーがフォローしているユーザーを取得
            recommended_users = User.objects.filter(
                profile__in=following_users
            ).exclude(
                id__in=[self.user.id] + [user.id for user in following_users]
            ).annotate(
                common_followers=models.Count('profile')
            ).order_by('-common_followers')[:limit]

            # 音楽の相性スコアを計算して追加
            recommendations = []
            for user in recommended_users:
                compatibility_score = self.get_music_compatibility_score(user)
                recommendations.append({
                    'user': user,
                    'compatibility_score': compatibility_score,
                    'common_interests': self.get_common_music_interests(user)
                })

            # 相性スコアで並び替え
            recommendations.sort(key=lambda x: x['compatibility_score'], reverse=True)
            return recommendations

        except Exception as e:
            logger.error(f"おすすめユーザーの取得に失敗: {str(e)}")
            return []

class MusicPost(models.Model):
    MOOD_CHOICES = [
        ('happy', '楽しい'),
        ('sad', '悲しい'),
        ('excited', 'テンション高め'),
        ('relaxed', 'リラックス'),
        ('energetic', 'エネルギッシュ'),
        ('calm', '穏やか'),
        ('romantic', 'ロマンティック'),
        ('nostalgic', 'ノスタルジック'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=200)
    artist = models.CharField(max_length=200)
    spotify_link = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image = models.URLField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    likes = models.ManyToManyField(User, related_name='liked_posts', blank=True)
    mood = models.CharField(max_length=50, choices=MOOD_CHOICES, blank=True)
    is_playlist_track = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.title} by {self.artist}"

    class Meta:
        ordering = ['-created_at']

    def get_engagement_score(self):
        """投稿のエンゲージメントスコアを計算"""
        comment_weight = 2  # コメントは「いいね」の2倍の重み
        return self.likes.count() + (self.comments.count() * comment_weight)

    def get_similar_posts(self):
        """類似の投稿を取得"""
        return MusicPost.objects.filter(
            Q(artist=self.artist) |
            Q(tags__overlap=self.tags) |
            Q(mood=self.mood)
        ).exclude(id=self.id)[:5]

class Comment(models.Model):
    post = models.ForeignKey(MusicPost, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.username}のコメント on {self.post.title}'


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
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='music_taste')
    genres = models.JSONField(default=list, blank=True)
    moods = models.JSONField(default=list, blank=True)
    favorite_artists = models.JSONField(default=list, blank=True)

    @property
    def top_genres(self):
        """
        ジャンルのリストを辞書形式に変換して返す
        """
        if not self.genres:
            return {}
        return {genre: 1 for genre in self.genres}

    @property
    def top_moods(self):
        """
        ムードのリストを辞書形式に変換して返す
        """
        if not self.moods:
            return {}
        return {mood: 1 for mood in self.moods}

    def __str__(self):
        return f"{self.user.username}の音楽の好み"

class MusicStory(models.Model):
    LISTENING_STATUS_CHOICES = [
        ('now_playing', '今聴いている'),
        ('just_discovered', '発見した'),
        ('recommendation', 'おすすめ'),
        ('memory', '思い出の一曲'),
    ]

    THEME_CHOICES = [
        ('default', 'デフォルト'),
        ('wave', '波形'),
        ('stars', '星空'),
        ('gradient', 'グラデーション'),
        ('vinyl', 'レコード'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='stories')
    title = models.CharField(max_length=100)
    artist = models.CharField(max_length=100)
    spotify_track_id = models.CharField(max_length=100, blank=True, null=True)
    album_art = models.URLField(blank=True, null=True)
    preview_url = models.URLField(blank=True, null=True)
    mood = models.CharField(max_length=50, blank=True, null=True)
    mood_emoji = models.CharField(max_length=10, blank=True, null=True)
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    track_name = models.CharField(max_length=100, blank=True, null=True)
    artist_name = models.CharField(max_length=100, blank=True, null=True)
    album_image_url = models.URLField(blank=True, null=True)
    
    # 追加フィールド
    viewers = models.ManyToManyField(User, related_name='viewed_stories', blank=True)
    quick_reactions = models.JSONField(default=dict)
    background_theme = models.CharField(max_length=20, choices=THEME_CHOICES, default='default')
    listening_status = models.CharField(max_length=20, choices=LISTENING_STATUS_CHOICES)
    
    class Meta:
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = self.created_at + timedelta(hours=24)
        super().save(*args, **kwargs)
    
    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

class StoryView(models.Model):
    story = models.ForeignKey(MusicStory, on_delete=models.CASCADE, related_name='views')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    viewed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('story', 'user')

class Music(models.Model):
    title = models.CharField(max_length=200, verbose_name='曲名')
    artist = models.CharField(max_length=200, verbose_name='アーティスト')
    album_art = models.URLField(verbose_name='アルバムアート', blank=True, null=True)
    spotify_id = models.CharField(max_length=100, unique=True, verbose_name='Spotify ID')
    preview_url = models.URLField(verbose_name='プレビューURL', blank=True, null=True)
    duration_ms = models.IntegerField(verbose_name='再生時間(ms)', default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '楽曲'
        verbose_name_plural = '楽曲'

    def __str__(self):
        return f"{self.title} - {self.artist}"

class Playlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='playlists')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    likes = models.ManyToManyField(User, related_name='liked_playlists', blank=True)
    
    def __str__(self):
        return self.title
    
    def get_engagement_score(self):
        """プレイリストのエンゲージメントスコアを計算"""
        comment_weight = 2  # コメントは「いいね」の2倍の重み
        return self.likes.count() + (self.playlist_comments.count() * comment_weight)


class PlaylistComment(models.Model):
    playlist = models.ForeignKey(Playlist, on_delete=models.CASCADE, related_name='playlist_comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.username}のコメント on {self.playlist.title}'

    class Meta:
        ordering = ['-created_at']

class PlaylistMusic(models.Model):
    playlist = models.ForeignKey(Playlist, on_delete=models.CASCADE, verbose_name='プレイリスト')
    music = models.ForeignKey(Music, on_delete=models.CASCADE, verbose_name='楽曲')
    order = models.IntegerField(default=0, verbose_name='順番')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'プレイリスト楽曲'
        verbose_name_plural = 'プレイリスト楽曲'
        ordering = ['order']
        unique_together = ['playlist', 'music']

    def __str__(self):
        return f"{self.playlist.title} - {self.music.title}"

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
