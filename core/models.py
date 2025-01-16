from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField(max_length=500, blank=True)
    followers = models.ManyToManyField(User, related_name='following', blank=True)

    def __str__(self):
        return f'{self.user.username}のプロフィール'

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

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()
