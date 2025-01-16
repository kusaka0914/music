from django.contrib import admin
from .models import Profile, MusicPost, Comment, MusicStory

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'spotify_connected']
    search_fields = ['user__username']

@admin.register(MusicPost)
class MusicPostAdmin(admin.ModelAdmin):
    list_display = ['title', 'artist', 'user', 'created_at']
    list_filter = ['created_at', 'mood']
    search_fields = ['title', 'artist', 'description']
    readonly_fields = ['created_at']

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['user', 'post', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username', 'content']

@admin.register(MusicStory)
class MusicStoryAdmin(admin.ModelAdmin):
    list_display = ['title', 'artist', 'user', 'listening_status', 'created_at', 'expires_at']
    list_filter = ['listening_status', 'mood', 'created_at']
    search_fields = ['title', 'artist', 'user__username']
    readonly_fields = ['created_at', 'expires_at']
