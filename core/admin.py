from django.contrib import admin
from .models import Profile, MusicPost, Comment, Playlist, Notification, MusicTaste

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'bio']
    search_fields = ['user__username', 'bio']

@admin.register(MusicPost)
class MusicPostAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'artist', 'created_at']
    search_fields = ['title', 'artist', 'description']
    readonly_fields = ['created_at']
    list_filter = ['created_at']

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['user', 'post', 'content', 'created_at']
    search_fields = ['content']
    readonly_fields = ['created_at']

@admin.register(Playlist)
class PlaylistAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'is_public', 'created_at']
    search_fields = ['title', 'description']
    readonly_fields = ['created_at']
    list_filter = ['is_public', 'created_at']

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'notification_type', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    readonly_fields = ['created_at']

@admin.register(MusicTaste)
class MusicTasteAdmin(admin.ModelAdmin):
    list_display = ['user', 'favorite_artists']
    search_fields = ['favorite_artists']
