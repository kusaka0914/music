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
    avatar = models.ImageField(upload_to='avatars/', default='default.jpg', null=True, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    website = models.URLField(max_length=200, blank=True)
    favorite_genres = models.JSONField(default=list, blank=True)
    favorite_artists = models.JSONField(default=list, blank=True)
    music_mood_preferences = models.JSONField(default=dict, blank=True)
    nickname = models.CharField(max_length=50, blank=True)
    following = models.ManyToManyField('self', symmetrical=False, related_name='followers', blank=True)
    spotify_refresh_token = models.CharField(max_length=255, null=True, blank=True)
    spotify_connected = models.BooleanField(default=False)
    music_taste = models.JSONField(default=dict, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username}のプロフィール"

    def get_music_compatibility_with_user(self, other_user):
        """他のユーザーとの音楽の相性を計算"""
        return self.get_music_compatibility_score(other_user)

    def get_music_compatibility_score(self, other_user):
        """他のユーザーとの音楽の相性スコアを計算（0-100）"""
        try:
            score = 0
            
            # アーティストの比較（15ポイント/アーティスト）
            my_artists = self.favorite_artists
            other_artists = other_user.profile.favorite_artists
            
            if not my_artists or not other_artists:
                return 0

            my_artist_names = set(artist['name'] for artist in my_artists)
            other_artist_names = set(artist['name'] for artist in other_artists)
            artist_match = len(my_artist_names & other_artist_names)
            score += artist_match * 15  # 共通のアーティストごとに15ポイント
            
            # 投稿の傾向を比較（5ポイント/ムード）
            my_posts = MusicPost.objects.filter(user=self.user)
            other_posts = MusicPost.objects.filter(user=other_user)
            
            my_moods = {post.post_type for post in my_posts}
            other_moods = {post.post_type for post in other_posts}
            mood_match = len(my_moods & other_moods)
            score += mood_match * 5  # 共通のムードごとに5ポイント
            
            # スコアを0-100の範囲に正規化
            return min(100, score)

        except Exception as e:
            logger.error(f"音楽の相性スコアの計算に失敗: {str(e)}")
            return 0

    def get_common_music_interests(self, other_user):
        """他のユーザーとの共通の音楽趣味を取得"""
        try:
            my_artists = self.favorite_artists
            other_artists = other_user.profile.favorite_artists

            if not my_artists or not other_artists:
                return {
                    'artists': [],
                    'moods': [],
                    'score': 0
                }

            # アーティスト名をキーとした辞書を作成
            my_artists_dict = {artist['name']: artist for artist in my_artists}
            other_artists_dict = {artist['name']: artist for artist in other_artists}
            
            # 共通のアーティスト名を見つける
            common_artist_names = set(my_artists_dict.keys()) & set(other_artists_dict.keys())
            
            # 共通のアーティストの完全な情報を取得
            common_artists = [my_artists_dict[name] for name in common_artist_names]

            # 共通のムードを取得
            my_posts = MusicPost.objects.filter(user=self.user)
            other_posts = MusicPost.objects.filter(user=other_user)
            my_moods = {post.post_type for post in my_posts}
            other_moods = {post.post_type for post in other_posts}
            common_moods = list(my_moods & other_moods)

            # スコアを計算
            score = self.get_music_compatibility_score(other_user)

            return {
                'artists': common_artists[:5],  # 上位5アーティストまで
                'moods': common_moods,
                'score': score
            }
        except Exception as e:
            logger.error(f"共通の音楽趣味の取得に失敗: {str(e)}")
            return {
                'artists': [],
                'moods': [],
                'score': 0
            }

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

    def get_top_genres(self):
        """ユーザーのトップジャンルを取得"""
        if not self.favorite_genres:
            return []
        return self.favorite_genres

class MusicPost(models.Model):
    TARGET_TYPE_CHOICES = [
        ('track', '曲について'),
        ('artist', 'アーティストについて'),
        ('album', 'アルバムについて'),
    ]

    POST_TYPE_CHOICES = [
        # 曲の投稿タイプ
        ('lyrics_analysis', '歌詞考察'),
        ('track_impression', '感想共有'),
        ('track_memory', '思い出共有'),
        # アーティストの投稿タイプ
        ('artist_introduction', 'アーティスト紹介'),
        ('artist_impression', '感想共有'),
        ('artist_memory', '思い出共有'),
        # アルバムの投稿タイプ
        ('album_review', 'アルバムレビュー'),
        ('album_impression', '感想共有'),
        ('album_memory', '思い出共有'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    target_type = models.CharField(max_length=50, choices=TARGET_TYPE_CHOICES)
    post_type = models.CharField(max_length=50, choices=POST_TYPE_CHOICES)
    
    # 曲の場合
    title = models.CharField(max_length=200, null=True, blank=True)
    artist = models.CharField(max_length=200, null=True, blank=True)
    spotify_track_id = models.CharField(max_length=200, null=True, blank=True)
    
    # アーティストの場合
    artist_name = models.CharField(max_length=200, null=True, blank=True)
    spotify_artist_id = models.CharField(max_length=200, null=True, blank=True)
    
    # アルバムの場合
    album_name = models.CharField(max_length=200, null=True, blank=True)
    album_artist = models.CharField(max_length=200, null=True, blank=True)
    spotify_album_id = models.CharField(max_length=200, null=True, blank=True)
    spotify_link = models.CharField(max_length=200)   
    # 共通フィールド
    description = models.TextField(blank=True)
    image = models.URLField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    likes = models.ManyToManyField(User, related_name='liked_posts', blank=True)
    is_playlist_track = models.BooleanField(default=False)

    def __str__(self):
        if self.target_type == 'track':
            return f"Track: {self.title} by {self.artist}"
        elif self.target_type == 'artist':
            return f"Artist: {self.artist_name}"
        else:  # album
            return f"Album: {self.album_name} by {self.album_artist}"

    class Meta:
        ordering = ['-created_at']

    def get_engagement_score(self):
        """投稿のエンゲージメントスコアを計算"""
        comment_weight = 2  # コメントは「いいね」の2倍の重み
        return self.likes.count() + (self.comments.count() * comment_weight)

    def get_similar_posts(self):
        """類似の投稿を取得"""
        return MusicPost.objects.filter(
            Q(target_type=self.target_type) &
            (
                Q(artist=self.artist) if self.target_type == 'track' else
                Q(artist_name=self.artist_name) if self.target_type == 'artist' else
                Q(album_artist=self.album_artist)
            )
        ).exclude(id=self.id)[:5]

class Comment(models.Model):
    post = models.ForeignKey(MusicPost, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.username}のコメント on {self.post.title}'


class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('follow', 'フォロー'),
        ('like_post', '投稿へのいいね'),
        ('comment_post', '投稿へのコメント'),
        ('like_playlist', 'プレイリストへのいいね'),
    )

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_notifications')
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    post = models.ForeignKey('MusicPost', on_delete=models.CASCADE, null=True, blank=True)
    playlist = models.ForeignKey('Playlist', on_delete=models.CASCADE, null=True, blank=True)
    comment = models.ForeignKey('Comment', on_delete=models.CASCADE, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.sender.username}から{self.get_notification_type_display()}"

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

class Event(models.Model):
    title = models.CharField(max_length=200)
    date = models.DateTimeField()
    venue = models.CharField(max_length=200)
    image = models.ImageField(upload_to='event_images/', null=True, blank=True)
    description = models.TextField()
    artists = models.JSONField()  # アーティスト名のリストを保存
    ticket_url = models.URLField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['date']

    @classmethod
    def get_upcoming_events(cls, artist_names=None):
        """
        開催予定のイベントを取得
        artist_names: 特定のアーティストのイベントのみを取得する場合に指定
        """
        events = cls.objects.filter(date__gte=timezone.now())
        if artist_names:
            # JSONFieldの中のアーティスト名でフィルタリング
            events = events.filter(artists__contains=artist_names)
        return events.order_by('date')

class MessageAttachment(models.Model):
    message = models.ForeignKey('Message', on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='message_attachments/')
    file_type = models.CharField(max_length=10)  # 'image', 'video', 'pdf'
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Attachment for message {self.message.id}'

    def save(self, *args, **kwargs):
        # ファイルタイプを自動判定
        file_name = self.file.name.lower()
        if file_name.endswith(('.jpg', '.jpeg', '.png', '.gif')):
            self.file_type = 'image'
        elif file_name.endswith(('.mp4', '.mov', '.avi')):
            self.file_type = 'video'
        elif file_name.endswith('.pdf'):
            self.file_type = 'pdf'
        else:
            self.file_type = 'other'
        super().save(*args, **kwargs)

class Message(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    content = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.sender.username} -> {self.recipient.username}: {self.content[:50]}'

class Conversation(models.Model):
    participants = models.ManyToManyField(User, related_name='conversations')
    last_message = models.ForeignKey(Message, on_delete=models.SET_NULL, null=True, blank=True, related_name='last_message_conversation')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"会話 {self.id}"

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
