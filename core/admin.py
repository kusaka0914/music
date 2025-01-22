from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import Profile, MusicPost, Comment, MusicStory, Playlist, PlaylistComment, PlaylistMusic, Music, Event, MusicTaste,Notification,Message

class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name = 'プロフィール'
    verbose_name_plural = 'プロフィール'

class CustomUserAdmin(UserAdmin):
    inlines = (ProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('-date_joined',)

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'nickname', 'spotify_connected', 'get_followers_count', 'get_following_count')
    search_fields = ('user__username', 'nickname')
    list_filter = ()
    fieldsets = (
        ('ユーザー情報', {
            'fields': ('user', 'nickname', 'bio', 'avatar')
        }),
        ('Spotify連携', {
            'fields': ('spotify_refresh_token', 'favorite_genres', 'favorite_artists', 'music_mood_preferences')
        }),
        ('ウェブサイト', {
            'fields': ('website',)
        })
    )

    def get_followers_count(self, obj):
        return obj.followers.count()
    get_followers_count.short_description = 'フォロワー数'

    def get_following_count(self, obj):
        return obj.following.count()
    get_following_count.short_description = 'フォロー中'

@admin.register(MusicPost)
class MusicPostAdmin(admin.ModelAdmin):
    list_display = ['title', 'artist', 'user', 'created_at', 'get_likes_count']
    list_filter = ['post_type', 'created_at']
    search_fields = ['title', 'artist', 'description']
    readonly_fields = ['created_at']

    def get_likes_count(self, obj):
        return obj.likes.count()
    get_likes_count.short_description = 'いいね数'

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('user', 'post', 'content_preview', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'content', 'post__title')
    readonly_fields = ('created_at',)
    fieldsets = (
        ('コメント情報', {
            'fields': ('user', 'post', 'content')
        }),
        ('タイムスタンプ', {
            'fields': ('created_at',)
        })
    )

    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'コメント内容'

@admin.register(MusicStory)
class MusicStoryAdmin(admin.ModelAdmin):
    list_display = ('title', 'artist', 'user', 'listening_status', 'created_at', 'expires_at', 'get_viewers_count')
    list_filter = ('listening_status', 'mood', 'created_at')
    search_fields = ('title', 'artist', 'user__username')
    readonly_fields = ('created_at', 'expires_at', 'get_viewers_count')
    fieldsets = (
        ('基本情報', {
            'fields': ('user', 'title', 'artist')
        }),
        ('ストーリー情報', {
            'fields': ('spotify_track_id', 'mood', 'listening_status', 'comment')
        }),
        ('表示情報', {
            'fields': ('created_at', 'expires_at', 'viewers')
        })
    )

    def get_viewers_count(self, obj):
        return obj.viewers.count()
    get_viewers_count.short_description = '閲覧者数'

# 既存のUserAdminを上書き
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

class PlaylistAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'created_at', 'get_engagement_score']
    list_filter = ['created_at']
    search_fields = ['title', 'user__username']
    readonly_fields = ['created_at']

    def get_engagement_score(self, obj):
        return obj.get_engagement_score()
    get_engagement_score.short_description = 'エンゲージメントスコア'

admin.site.register(Playlist, PlaylistAdmin)

@admin.register(PlaylistComment)
class PlaylistCommentAdmin(admin.ModelAdmin):
    list_display = ('playlist', 'user', 'content', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('playlist__title', 'user__username', 'content')
    readonly_fields = ('created_at',)

@admin.register(PlaylistMusic)
class PlaylistMusicAdmin(admin.ModelAdmin):
    list_display = ('playlist', 'music', 'order')
    list_filter = ('playlist', 'music')
    search_fields = ('playlist__title', 'music__title')
    readonly_fields = ('order',)

@admin.register(Music)
class MusicAdmin(admin.ModelAdmin):
    list_display = ('title', 'artist', 'album_art')
    search_fields = ('title', 'artist')

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'date', 'venue')
    search_fields = ('title', 'artists')
    list_filter = ('date', 'venue')
    ordering = ('date',)

@admin.register(MusicTaste)
class MusicTasteAdmin(admin.ModelAdmin):
    list_display = ('user', 'genres', 'moods', 'favorite_artists')
    search_fields = ('user__username',)
    list_filter = ('genres', 'moods', 'favorite_artists')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'sender', 'notification_type', 'post', 'playlist', 'comment', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('recipient__username', 'sender__username', 'notification_type', 'post__title', 'playlist__title', 'comment__content')
    readonly_fields = ('created_at',)

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'recipient', 'content', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('sender__username', 'recipient__username', 'content')
    readonly_fields = ('created_at',)
