from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import MusicPost, Comment, Playlist, Notification, Profile

@receiver(m2m_changed, sender=Profile.following.through)
def create_follow_notification(sender, instance, action, pk_set, **kwargs):
    if action == "post_add":
        for pk in pk_set:
            followed_profile = Profile.objects.get(pk=pk)
            Notification.objects.create(
                recipient=followed_profile.user,
                sender=instance.user,
                notification_type='follow'
            )

@receiver(m2m_changed, sender=MusicPost.likes.through)
def create_post_like_notification(sender, instance, action, pk_set, **kwargs):
    if action == "post_add":
        for pk in pk_set:
            if instance.user.id != pk:  # 自分の投稿へのいいねは通知しない
                Notification.objects.create(
                    recipient=instance.user,
                    sender=User.objects.get(pk=pk),
                    notification_type='like_post',
                    post=instance
                )

@receiver(post_save, sender=Comment)
def create_comment_notification(sender, instance, created, **kwargs):
    if created and instance.user != instance.post.user:  # 自分の投稿へのコメントは通知しない
        Notification.objects.create(
            recipient=instance.post.user,
            sender=instance.user,
            notification_type='comment_post',
            post=instance.post,
            comment=instance
        )

@receiver(m2m_changed, sender=Playlist.likes.through)
def create_playlist_like_notification(sender, instance, action, pk_set, **kwargs):
    if action == "post_add":
        for pk in pk_set:
            if instance.user.id != pk:  # 自分のプレイリストへのいいねは通知しない
                Notification.objects.create(
                    recipient=instance.user,
                    sender=User.objects.get(pk=pk),
                    notification_type='like_playlist',
                    playlist=instance
                ) 