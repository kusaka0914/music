from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.db.models import Q, Count, Case, When, F, Model as models, Exists, OuterRef, IntegerField
from django.contrib import messages
from django.contrib.auth.models import User
from django.conf import settings
from .models import (
    MusicPost, MusicStory, Comment, Profile, MusicTaste,
    Playlist, Notification, PlaylistComment, Music, PlaylistMusic, Event,
    Conversation, Message
)
from .forms import MusicPostForm, MusicStoryForm, CommentForm, MusicTasteForm, ProfileEditForm, MusicStoryForm,UserLoginForm,UserRegisterForm,PlaylistForm
from .spotify_utils import get_spotify_client, get_recently_played_tracks, get_top_tracks, get_spotify_oauth
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
import json
import logging
from django.contrib.auth import login, logout
from django.core.paginator import Paginator
import random
from django.db import transaction
import pytz

logger = logging.getLogger(__name__)


def home(request):
    # 検索クエリの取得
    search_query = request.GET.get('q', '')
    
    # 特定の投稿IDが指定された場合、その投稿を取得
    featured_post_id = request.GET.get('featured')
    featured_post = None
    if featured_post_id:
        try:
            featured_post = MusicPost.objects.select_related('user', 'user__profile').prefetch_related('likes', 'comments').get(
                id=featured_post_id,
                user__isnull=False,
                user__username__isnull=False
            )
        except MusicPost.DoesNotExist:
            pass

    # 通常の投稿を取得（ユーザー名が存在するものだけ）
    posts = MusicPost.objects.select_related('user', 'user__profile').prefetch_related('likes', 'comments').filter(
        user__isnull=False,
        user__username__isnull=False
    )
    
    # 特定の投稿が指定されている場合、その投稿を除外して取得
    if featured_post:
        posts = posts.exclude(id=featured_post.id)
    
    # 投稿を作成日時の降順で並び替え
    posts = posts.order_by('-created_at')

    # 特定の投稿が存在する場合、リストの先頭に追加
    if featured_post:
        posts = list(posts)
        posts.insert(0, featured_post)
    
    # Ajaxリクエストの場合、投稿リストのみを返す
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('core/includes/post_list.html', {'posts': posts}, request=request)
        return JsonResponse({'html': html})
    
    # 通常のリクエストの場合は以下の処理を続行
    # アクティブなストーリーを取得（24時間以内）
    active_stories = MusicStory.objects.filter(
        expires_at__gt=timezone.now(),
        user__isnull=False,
        user__username__isnull=False
    ).select_related('user', 'user__profile').order_by('-created_at')
    
    # ストーリーをユーザーごとにグループ化
    stories_by_user = {}
    for story in active_stories:
        if story.user and story.user.username:  # ユーザーとユーザー名の存在を確認
            if story.user not in stories_by_user:
                stories_by_user[story.user] = {
                    'user': {
                        'username': story.user.username,
                        'avatar_url': story.user.profile.avatar.url if story.user.profile.avatar else '/static/images/default-avatar.svg',
                    },
                    'stories': [],
                        'has_unviewed': False
                }
        
        story_info = {
            'id': story.id,
            'track_name': story.track_name or '',
            'artist_name': story.artist_name or '',
            'album_image_url': story.album_image_url or '',
            'mood': story.mood or '',
            'mood_emoji': story.mood_emoji or '',
            'comment': story.comment or '',
            'created_at': story.created_at.isoformat(),
                'viewed': request.user.is_authenticated and request.user in story.viewers.all()
        }
        stories_by_user[story.user]['stories'].append(story_info)
        
        if request.user.is_authenticated and not story_info['viewed']:
                stories_by_user[story.user]['has_unviewed'] = True
    
    # stories_by_userをリスト形式に変換
    stories_by_user_list = [data for data in stories_by_user.values() if data['user']['username']]
    
    # トレンド投稿を取得（コメントの重みを3倍に設定）
    trending_posts = MusicPost.objects.select_related('user', 'user__profile').prefetch_related('likes', 'comments').filter(
        created_at__gte=timezone.now() - timezone.timedelta(days=7),
        user__isnull=False,
        user__username__isnull=False
    ).annotate(
        like_count=Count('likes'),
        comment_count=Count('comments'),
        engagement_score=Count('likes') + (Count('comments') * 3)  # コメントの重みを3倍に
    ).order_by('-engagement_score', '-created_at')[:5]
    
    # おすすめユーザーを取得
    recommended_users = []
    if request.user.is_authenticated:
        # フォロー中のユーザーのプロフィールIDを取得
        following_profile_ids = request.user.profile.following.values_list('id', flat=True)
        
        # 自分以外のユーザーを取得（フォロー中のユーザーを除外）
        other_users = Profile.objects.exclude(
            Q(user=request.user) |
            Q(id__in=following_profile_ids)
        ).select_related('user').filter(
            user__isnull=False  # ユーザーが存在するものだけを取得
        )
        
        # 各ユーザーとの音楽の相性を計算
        for profile in other_users:
            if profile.user and profile.user.username:  # ユーザーとユーザー名が存在する場合のみ処理
                compatibility = calculate_music_compatibility(request.user.profile, profile)
                # 音楽の相性が15%以上のユーザーのみを追加
                if compatibility['score'] >= 15:
                    recommended_users.append({
                        'user': profile.user,
                        'compatibility_score': compatibility['score']
                    })
        
        # 互換性スコアで降順ソート
        recommended_users.sort(key=lambda x: x['compatibility_score'], reverse=True)
        # 上位5人まで取得
        recommended_users = recommended_users[:5]
    
    # おすすめのプレイリストを取得
    recommended_playlists = Playlist.objects.filter(
        is_public=True
    ).annotate(
        track_count=Count('playlistmusic'),
        likes_count=Count('likes'),
        engagement_score=Count('likes') + Count('playlist_comments')
    ).select_related(
        'user', 'user__profile'
    ).prefetch_related(
        'playlistmusic_set__music'
    ).order_by('-engagement_score', '-created_at')[:6]

    # プレイリストのカバー画像を設定
    for playlist in recommended_playlists:
        first_track = playlist.playlistmusic_set.first()
        if first_track:
            playlist.cover_image = first_track.music.album_art
        else:
            playlist.cover_image = None

    context = {
        'posts': posts,
        'stories_by_user': stories_by_user_list,
        'trending_posts': trending_posts,
        'recommended_users': recommended_users,  # 上位3人のみ表示
        'recommended_playlists': recommended_playlists  # おすすめのプレイリストを追加
    }
    
    return render(request, 'core/home.html', context)

def register_view(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                # プロフィールが存在しない場合のみ作成
                Profile.objects.get_or_create(user=user)
                messages.success(request, '登録が完了しました。ログインしてください。')
                return redirect('core:login')
            except Exception as e:
                messages.error(request, '登録中にエラーが発生しました。')
                return redirect('core:register')
    else:
        form = UserRegisterForm()
    return render(request, 'core/register.html', {'form': form})

def calculate_music_compatibility(user1, user2):
    """ユーザー間の音楽の相性スコアを計算"""
    try:
        score = 0
        common_artists = []
        common_tracks = []
        
        # お気に入りアーティストを比較
        user1_artists = [artist['name'] for artist in user1.favorite_artists]
        user2_artists = [artist['name'] for artist in user2.favorite_artists]
    
        common_artists = [artist for artist in user1_artists if artist in user2_artists]
        score += len(common_artists) * 15  # 共通のアーティストごとに15ポイント
        
        # スコアを0-100の範囲に正規化
        normalized_score = min(100, score)
        
        return {
            'score': normalized_score,
            'common_artists': common_artists[:5],  # 上位5アーティストまで
        }
    except Exception as e:
        logger.error(f"音楽の相性スコア計算エラー: {str(e)}")
        return {
            'score': 0,
            'common_artists': [],
        }

def get_common_artists(user1, user2):
    """二人のユーザー間の共通のアーティストを取得"""
    try:
        taste1, _ = MusicTaste.objects.get_or_create(user=user1)
        taste2, _ = MusicTaste.objects.get_or_create(user=user2)
        return list(set(taste1.top_artists.keys()) & set(taste2.top_artists.keys()))
    except Exception as e:
        logger.error(f"共通アーティスト取得エラー: {str(e)}")
        return []

def login_view(request):
    if request.method == 'POST':
        form = UserLoginForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, 'ログインしました。')
            return redirect('core:home')
    else:
        form = UserLoginForm()
    return render(request, 'core/login.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.success(request, 'ログアウトしました。')
    return redirect('core:home')

def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                # プロフィールが存在しない場合のみ作成
                Profile.objects.get_or_create(user=user)
                messages.success(request, '登録が完了しました。ログインしてください。')
                return redirect('core:login')
            except Exception as e:
                messages.error(request, '登録中にエラーが発生しました。')
                return redirect('core:register')
    else:
        form = UserRegisterForm()
    return render(request, 'core/register.html', {'form': form})

@login_required
def create_post(request):
    if request.method == 'POST':
        try:
            # フォームデータの取得
            post_type = request.POST.get('post_type')
            description = request.POST.get('description')
            
            # バリデーション
            if not all([post_type, description]):
                messages.error(request, '必須項目が入力されていません。')
                return redirect('core:create_post')

            # 投稿データの準備
            post_data = {
                'user': request.user,
                'description': description,
                'post_type': post_type,
            }

            # 投稿タイプに応じてデータを設定
            if 'spotify_track_id' in request.POST:
                spotify_track_id = request.POST.get('spotify_track_id')
                post_data.update({
                    'title': request.POST.get('title'),
                    'artist': request.POST.get('artist'),
                    'spotify_link': f"https://open.spotify.com/track/{spotify_track_id}",
                    'image': request.POST.get('image')
                })
            elif 'spotify_artist_id' in request.POST:
                spotify_artist_id = request.POST.get('spotify_artist_id')
                artist_name = request.POST.get('artist_name')
                
                # アーティスト投稿の場合
                post_data.update({
                    'artist': artist_name,  # artist_nameをartistフィールドに保存
                    'spotify_link': f"https://open.spotify.com/artist/{spotify_artist_id}",
                    'image': request.POST.get('image'),
                    'target_type': 'artist'  # target_typeを明示的に設定
                })
            elif 'spotify_album_id' in request.POST:
                spotify_album_id = request.POST.get('spotify_album_id')
                post_data.update({
                    'title': request.POST.get('album_name'),
                    'artist': request.POST.get('album_artist'),
                    'spotify_link': f"https://open.spotify.com/album/{spotify_album_id}",
                    'image': request.POST.get('image'),
                    'target_type': 'album'  # target_typeを明示的に設定
                })

            # 投稿の作成
            post = MusicPost.objects.create(**post_data)

            messages.success(request, '投稿が作成されました！')
            return redirect('core:home')

        except Exception as e:
            logger.error(f"投稿作成中にエラーが発生: {str(e)}")
            messages.error(request, '投稿の作成中にエラーが発生しました。')
            return redirect('core:create_post')

    return render(request, 'core/post_form.html')

@login_required
def post_detail(request, post_id):
    post = get_object_or_404(MusicPost, id=post_id)
    comments = post.comments.select_related('user').order_by('-created_at')
    
    if request.method == 'POST':
        comment_form = CommentForm(request.POST)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.user = request.user
            comment.post = post
            comment.save()
            return redirect('core:post_detail', post_id=post.id)
    else:
        comment_form = CommentForm()
    
    # 類似投稿を取得（同じアーティストまたは同じムードの投稿）
    similar_posts = MusicPost.objects.filter(
        Q(artist=post.artist) |
        Q(mood=post.mood)
    ).exclude(id=post.id).order_by('-created_at')[:5]
    
    context = {
        'post': post,
        'comments': comments,
        'comment_form': comment_form,
        'similar_posts': similar_posts,
    }
    
    return render(request, 'core/post_detail.html', context)

@login_required
def edit_post(request, pk):
    post = get_object_or_404(MusicPost, pk=pk, user=request.user)
    if request.method == 'POST':
        form = MusicPostForm(request.POST, instance=post)
        if form.is_valid():
            form.save()
            messages.success(request, '投稿が更新されました。')
            return redirect('core:post_detail', pk=post.pk)
    else:
        form = MusicPostForm(instance=post)
    return render(request, 'core/post_form.html', {'form': form, 'title': '投稿を編集'})

@login_required
def delete_post(request, pk):
    post = get_object_or_404(MusicPost, pk=pk, user=request.user)
    if request.method == 'POST':
        post.delete()
        messages.success(request, '投稿が削除されました。')
        return redirect('core:home')
    return render(request, 'core/post_confirm_delete.html', {'post': post})

@login_required
def like_post(request, post_id):
    try:
        with transaction.atomic():
            post = MusicPost.objects.select_for_update().get(id=post_id)
            if request.user in post.likes.all():
                post.likes.remove(request.user)
                liked = False
            else:
                post.likes.add(request.user)
                liked = True
            
            return JsonResponse({
                'status': 'success',
                'liked': liked,
                'like_count': post.likes.count()
            })
    except MusicPost.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': '投稿が見つかりません。'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': 'エラーが発生しました。'
        }, status=500)

@login_required
def add_comment(request, pk):
    post = get_object_or_404(MusicPost, pk=pk)
    if request.method == 'POST':
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.user = request.user
            comment.post = post
            comment.save()
            if request.user != post.user:
                Notification.objects.create(
                    recipient=post.user,
                    sender=request.user,
                    notification_type='comment',
                    post=post,
                    comment=comment
                )
            messages.success(request, 'コメントが投稿されました。')
            return redirect('core:post_detail', pk=post.pk)
    return redirect('core:post_detail', pk=post.pk)

@login_required
def profile(request, username):
    try:
        profile_user = User.objects.get(username=username)
        profile = profile_user.profile
        posts = MusicPost.objects.filter(user=profile_user).order_by('-created_at')
        
        # フォロー中とフォロワーのユーザーリストを取得
        following_users = User.objects.filter(profile__in=profile_user.profile.following.all())
        follower_users = User.objects.filter(profile__following=profile_user.profile)
        
        # プレイリストを取得
        playlists = Playlist.objects.filter(
            user=profile_user,
            is_public=True
        ).annotate(
            engagement=Count('likes') + Count('playlist_comments')
        ).order_by('-created_at')

        for playlist in playlists:
            playlist.cover_image = playlist.playlistmusic_set.first().music.album_art
        
        # Spotifyのデータを取得
        recently_played = []
        top_tracks = []
        if profile_user.profile.spotify_connected:
            try:
                spotify_client = get_spotify_client(profile_user)
                if spotify_client:
                    # 重複を除去するために、track_idをキーとして使用
                    recently_played_all = get_recently_played_tracks(spotify_client)
                    seen_tracks = set()
                    recently_played = []
                    for track in recently_played_all:
                        track_id = track.get('id')
                        if track_id not in seen_tracks:
                            seen_tracks.add(track_id)
                            recently_played.append(track)
                    top_tracks = get_top_tracks(spotify_client)
            except Exception as e:
                logger.error(f"Spotifyデータの取得に失敗: {str(e)}")
        
        # 音楽の相性スコアを計算（既存のユーザーの場合）
        compatibility_data = None
        
        # 各ユーザーとの音楽の相性を計算
        compatibility_data = calculate_music_compatibility(request.user.profile, profile)
        
        context = {
            'profile_user': profile_user,
            'posts': posts,
            'following_users': following_users,
            'follower_users': follower_users,
            'playlists': playlists,
            'recently_played': recently_played,
            'top_tracks': top_tracks,
            'compatibility_data': compatibility_data,
        }
        return render(request, 'core/profile.html', context)
    except User.DoesNotExist:
        return redirect('core:home')

@login_required
def follow_user(request, username):
    """ユーザーをフォロー/アンフォローする"""
    user_to_follow = get_object_or_404(User, username=username)
    if request.user != user_to_follow:
        if user_to_follow.profile in request.user.profile.following.all():
            request.user.profile.following.remove(user_to_follow.profile)
            is_following = False
        else:
            request.user.profile.following.add(user_to_follow.profile)
            is_following = True
            # 通知を作成
            Notification.objects.create(
                recipient=user_to_follow,
                sender=request.user,
                notification_type='follow'
            )
        
        return JsonResponse({
            'status': 'success',
            'is_following': is_following
        })
    return JsonResponse({'status': 'error', 'message': '自分自身をフォローすることはできません'}, status=400)

@login_required
def create_playlist(request):
    if request.method == 'POST':
        try:
            title = request.POST.get('title')
            description = request.POST.get('description')
            is_public = request.POST.get('is_public') == 'on'
            track_ids_str = request.POST.get('track_ids', '[]')
            
            try:
                track_ids = json.loads(track_ids_str)
            except json.JSONDecodeError:
                logger.error(f"track_idsのJSONデコードに失敗: {track_ids_str}")
                track_ids = []

            if not title:
                messages.error(request, 'プレイリスト名を入力してください。')
                return redirect('core:create_playlist')

            if not track_ids:
                messages.error(request, '少なくとも1曲は追加してください。')
                return redirect('core:create_playlist')

            # プレイリストの作成
            playlist = Playlist.objects.create(
                user=request.user,
                title=title,
                description=description,
                is_public=is_public
            )

            # 選択された曲をプレイリストに追加
            spotify = get_spotify_client()
            
            for order, track_id in enumerate(track_ids):
                try:
                    # 既存の楽曲を探す
                    music = Music.objects.filter(spotify_id=track_id).first()
                    if not music:
                        # Spotifyから曲の情報を取得して新しい楽曲を作成
                        track_info = spotify.track(track_id)
                        music = Music.objects.create(
                            title=track_info['name'],
                            artist=track_info['artists'][0]['name'],
                            spotify_id=track_id,
                            album_art=track_info['album']['images'][0]['url'] if track_info['album']['images'] else None,
                            preview_url=track_info.get('preview_url'),
                            duration_ms=track_info.get('duration_ms', 0)
                        )

                    # プレイリストと楽曲を関連付け
                    PlaylistMusic.objects.create(
                        playlist=playlist,
                        music=music,
                        order=order
                    )

                except Exception as e:
                    logger.error(f"楽曲の追加中にエラー: {str(e)}")
                    continue

            messages.success(request, 'プレイリストを作成しました。')
            return redirect('core:playlist_detail', pk=playlist.pk)

        except Exception as e:
            logger.error(f"プレイリスト作成エラー: {str(e)}")
            messages.error(request, 'プレイリストの作成中にエラーが発生しました。')
            return redirect('core:create_playlist')

    return render(request, 'core/create_playlist.html')

def playlist_detail(request, pk):
    playlist = get_object_or_404(Playlist, pk=pk)
    
    # プレイリストの曲を取得（順序を保持）
    playlist_tracks = PlaylistMusic.objects.filter(
        playlist=playlist
    ).select_related('music').order_by('order')
    
    # おすすめプレイリストを取得
    recommended_playlists = Playlist.objects.filter(
        is_public=True
    ).exclude(
        pk=pk
    ).annotate(
        track_count=Count('playlistmusic'),
        likes_count=Count('likes'),
        engagement_score=Count('likes') + Count('playlist_comments')
    ).select_related(
        'user', 'user__profile'
    ).prefetch_related(
        'playlistmusic_set__music'
    ).order_by('-engagement_score', '-created_at')[:5]

    
    first_track = playlist.playlistmusic_set.first()
    if first_track:
        playlist.cover_image = first_track.music.album_art
    else:
        playlist.cover_image = None

    for playlist_music in recommended_playlists:
        first_track = playlist_music.playlistmusic_set.first()
        if first_track:
            playlist_music.cover_image = first_track.music.album_art
        else:
            playlist_music.cover_image = None

    # Spotifyから人気の曲を取得
    try:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        # 日本の人気曲を検索（より多くの曲を取得してからランダムに選択）
        results = spotify.search(
            q='year:2024',
            type='track',
            market='JP',
            limit=20  # より多くの曲を取得
        )
        
        import random
        trending_tracks = []
        if 'tracks' in results and 'items' in results['tracks']:
            # ランダムに5曲を選択
            tracks = random.sample(results['tracks']['items'], min(5, len(results['tracks']['items'])))
            for track in tracks:
                track_data = {
                    'title': track['name'],
                    'artist': track['artists'][0]['name'] if track['artists'] else 'Unknown Artist',
                    'image': track['album']['images'][0]['url'] if track['album']['images'] else None,
                    'spotify_id': track['id']
                }
                trending_tracks.append(track_data)
            
    except Exception as e:
        logger.error(f"Spotifyからの人気曲取得エラー: {str(e)}")
        trending_tracks = []

    context = {
        'playlist': playlist,
        'playlist_tracks': playlist_tracks,
        'recommended_playlists': recommended_playlists,
        'trending_tracks': trending_tracks,
    }
    
    return render(request, 'core/playlist_detail.html', context)

@login_required
def edit_playlist(request, pk):
    playlist = get_object_or_404(Playlist, pk=pk, user=request.user)
    if request.method == 'POST':
        form = PlaylistForm(request.POST, instance=playlist)
        if form.is_valid():
            form.save()
            messages.success(request, 'プレイリストが更新されました。')
            return redirect('core:playlist_detail', pk=playlist.pk)
    else:
        form = PlaylistForm(instance=playlist)
    return render(request, 'core/playlist_form.html', {'form': form, 'title': 'プレイリストを編集'})

@login_required
def delete_playlist(request, pk):
    playlist = get_object_or_404(Playlist, pk=pk, user=request.user)
    if request.method == 'POST':
        playlist.delete()
        messages.success(request, 'プレイリストが削除されました。')
        return redirect('core:home')
    return render(request, 'core/playlist_confirm_delete.html', {'playlist': playlist})

@login_required
def add_to_playlist(request, post_pk, playlist_pk):
    post = get_object_or_404(MusicPost, pk=post_pk)
    playlist = get_object_or_404(Playlist, pk=playlist_pk, user=request.user)
    if post in playlist.posts.all():
        playlist.posts.remove(post)
        messages.success(request, f'「{post.title}」がプレイリストから削除されました。')
    else:
        playlist.posts.add(post)
        messages.success(request, f'「{post.title}」がプレイリストに追加されました。')
    return redirect('core:post_detail', pk=post_pk)

@login_required
def notifications(request):
    notifications = request.user.notifications.all()
    unread_count = notifications.filter(is_read=False).count()
    
    # 全ての通知を既読にする
    notifications.filter(is_read=False).update(is_read=True)
    
    return render(request, 'core/notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count
    })

@login_required
def get_unread_notification_count(request):
    count = request.user.notifications.filter(is_read=False).count()
    return JsonResponse({'count': count})

@login_required
def notification_redirect(request, notification_id):
    notification = get_object_or_404(Notification, id=notification_id)
    notification.is_read = True
    notification.save()
    
    if notification.notification_type == 'follow':
        return redirect('core:profile', username=notification.sender.username)
    elif notification.notification_type in ['like_post', 'comment_post']:
        return redirect(f'/?featured={notification.post.id}')
    elif notification.notification_type == 'like_playlist':
        return redirect('core:playlist_detail', playlist_id=notification.playlist.id)
    
    return redirect('core:home')

@login_required
def following_posts(request):
    following_users = request.user.profile.following.values_list('user', flat=True)
    posts = MusicPost.objects.filter(user__in=following_users).select_related('user', 'user__profile').prefetch_related('likes', 'comments').order_by('-created_at')
    return render(request, 'core/following_posts.html', {'posts': posts})

def search(request):
    query = request.GET.get('q', '')
    search_type = request.GET.get('type', 'all')  # 検索タイプ（all, posts, users, playlists）
    
    if query:
        if search_type == 'users':
            # ユーザー検索
            users = User.objects.filter(
                Q(username__icontains=query) |
                Q(profile__bio__icontains=query)
            ).select_related('profile').distinct()

            # ログインユーザーの場合、各ユーザーとの相性スコアとフォロー状態を計算
            if request.user.is_authenticated:
                users_with_compatibility = []
                for user in users:
                    if user != request.user:  # 自分自身を除外
                        compatibility = calculate_music_compatibility(request.user.profile, user.profile)
                        user.compatibility_score = compatibility['score']
                        # フォロー状態を追加
                        user.is_following = user.profile in request.user.profile.following.all()
                        users_with_compatibility.append(user)
                users = users_with_compatibility
            
            context = {
                'query': query,
                'search_type': search_type,
                'users': users
            }
            
        elif search_type == 'playlists':
            # プレイリスト検索
            playlists = Playlist.objects.filter(
                Q(title__icontains=query) |
                Q(description__icontains=query),
                is_public=True
            ).select_related('user', 'user__profile').annotate(
                track_count=Count('playlistmusic'),
                likes_count=Count('likes')
            ).order_by('-created_at')
            
            context = {
                'query': query,
                'search_type': search_type,
                'playlists': playlists
            }
            
        elif search_type == 'posts':
            # 投稿検索
            posts = MusicPost.objects.filter(
                Q(title__icontains=query) |
                Q(artist__icontains=query) |
                Q(description__icontains=query) |
                Q(mood__icontains=query)
            ).select_related('user', 'user__profile').prefetch_related(
                'likes', 'comments'
            ).order_by('-created_at')
            
            context = {
                'query': query,
                'search_type': search_type,
                'posts': posts
            }
            
        else:  # all
            # 全体検索
            posts = MusicPost.objects.filter(
                Q(title__icontains=query) |
                Q(artist__icontains=query) |
                Q(description__icontains=query)
            ).select_related('user', 'user__profile').prefetch_related(
                'likes', 'comments'
            ).order_by('-created_at')[:5]
            
            users = User.objects.filter(
                Q(username__icontains=query) |
                Q(profile__bio__icontains=query)
            ).select_related('profile').distinct()[:5]
            
            # ログインユーザーの場合、各ユーザーとの相性スコアとフォロー状態を計算
            if request.user.is_authenticated:
                users_with_compatibility = []
                for user in users:
                    if user != request.user:  # 自分自身を除外
                        compatibility = calculate_music_compatibility(request.user.profile, user.profile)
                        user.compatibility_score = compatibility['score']
                        # フォロー状態を追加
                        user.is_following = user.profile in request.user.profile.following.all()
                        users_with_compatibility.append(user)
                users = users_with_compatibility
            
            playlists = Playlist.objects.filter(
                Q(title__icontains=query) |
                Q(description__icontains=query),
                is_public=True
            ).select_related('user', 'user__profile').annotate(
                track_count=Count('playlistmusic'),
                likes_count=Count('likes')
            ).order_by('-created_at')[:5]

            for playlist in playlists:
                first_track = playlist.playlistmusic_set.first()
                if first_track:
                    playlist.cover_image = first_track.music.album_art
                else:
                    playlist.cover_image = None
            
            context = {
                'query': query,
                'search_type': search_type,
                'posts': posts,
                'users': users,
                'playlists': playlists
            }
    else:
        context = {
            'query': '',
            'search_type': search_type
        }
    
    return render(request, 'core/search.html', context)

@login_required
def profile_edit(request):
    if request.method == 'POST':
        form = ProfileEditForm(request.POST, request.FILES, instance=request.user.profile, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'プロフィールを更新しました。')
            return redirect('core:profile', username=request.user.username)
    else:
        form = ProfileEditForm(instance=request.user.profile, user=request.user)
    
    return render(request, 'core/profile_edit.html', {
        'form': form
    })

@login_required
def edit_music_taste(request):
    music_taste, created = Profile.objects.get_or_create(user=request.user)
    user = request.user
    
    if request.method == 'POST':
        # AJAXリクエストの場合
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            try:
                data = json.loads(request.body)
                action = data.get('action')
                
                if action == 'add_artist':
                    artist_name = data.get('artist')
                    artist_image = data.get('image')
                    artist_id = data.get('id')
                    
                    # favorite_artistsが未初期化の場合は空のリストを作成
                    if not user.profile.favorite_artists:
                        user.profile.favorite_artists = []
                    
                    # アーティストデータを作成
                    artist_data = {
                        'name': artist_name,
                        'image': artist_image,
                        'id': artist_id
                    }
                    
                    # IDで重複チェック
                    if not any(artist.get('id') == artist_id for artist in user.profile.favorite_artists):
                        user.profile.favorite_artists.append(artist_data)
                        user.profile.save()
                    
                    return JsonResponse({
                        'status': 'success',
                        'message': 'アーティストを追加しました'
                    })
                
                elif action == 'update_genres':
                    genres = data.get('genres', [])
                    user.profile.favorite_genres = genres
                    user.profile.save()
                    return JsonResponse({'status': 'success'})
                
                elif action == 'update_moods':
                    moods = data.get('moods', [])
                    user.profile.music_mood_preferences = moods
                    user.profile.save()
                    return JsonResponse({'status': 'success'})
                
                return JsonResponse({'status': 'error', 'message': '不明なアクション'})
            
            except json.JSONDecodeError:
                return JsonResponse({'status': 'error', 'message': '無効なJSONデータ'}, status=400)
            except Exception as e:
                logger.error(f"音楽の好み更新中にエラー: {str(e)}")
                return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
        
        # 通常のフォーム送信の場合
        else:
            form = MusicTasteForm(request.POST, instance=user.profile)
            if form.is_valid():
                form.save()
                messages.success(request, '音楽の好みを更新しました。')
                return redirect('core:profile', username=request.user.username)
    else:
        form = MusicTasteForm(instance=user.profile)
    
    # 利用可能なジャンルとムードのリスト
    available_genres = [
        'j-pop', 'j-rock', 'anime', 'pop', 'rock', 'hip-hop', 'r&b', 'jazz',
        'classical', 'electronic', 'dance', 'alternative', 'indie', 'metal',
        'folk', 'blues', 'reggae', 'soul', 'punk', 'country'
    ]
    
    available_moods = [
        'morning', 'night', 'rainy', 'workout', 'study', 'party',
        'relax', 'sad', 'happy', 'energetic', 'romantic', 'focus'
    ]
    
    # 現在の選択状態を取得
    current_genres = user.profile.favorite_genres if user.profile.favorite_genres else []
    current_moods = user.profile.music_mood_preferences if user.profile.music_mood_preferences else []
    current_artists = user.profile.favorite_artists if user.profile.favorite_artists else []
    
    # 人気のアーティストを取得
    try:
        logger.info("人気アーティストの取得を開始")
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        # J-POPアーティストの検索
        results = spotify.search(q='genre:j-pop year:2024', type='artist', market='JP', limit=10)
        popular_artists = []
        
        for artist in results['artists']['items']:
            artist_data = {
                'name': artist['name'],
                'id': artist['id'],
                'image': artist['images'][0]['url'] if artist['images'] else None,
                'genres': artist['genres'][:3] if artist['genres'] else []
            }
            popular_artists.append(artist_data)
            logger.info(f"アーティスト取得: {artist_data['name']}")
        
        logger.info(f"人気アーティスト取得完了: {len(popular_artists)}件")
    except Exception as e:
        logger.error(f"人気アーティストの取得に失敗: {str(e)}")
        popular_artists = []
    
    context = {
        'form': form,
        'available_genres': available_genres,
        'available_moods': available_moods,
        'current_genres': current_genres,
        'current_moods': current_moods,
        'current_artists': current_artists,
        'popular_artists': popular_artists
    }
    
    return render(request, 'core/edit_music_taste.html', context)

def search_artists(request):
    query = request.GET.get('q', '')
    if not query:
        return JsonResponse({'artists': []})
    
    try:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        results = spotify.search(q=query, type='artist', limit=5)
        artists = [{
            'name': artist['name'],
            'id': artist['id'],
            'image': artist['images'][0]['url'] if artist['images'] else None
        } for artist in results['artists']['items']]
        
        return JsonResponse({'artists': artists})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def music_compatibility(request):
    try:
        # ユーザーの音楽の好みを取得
        my_music_taste, _ = MusicTaste.objects.get_or_create(user=request.user)
        
        # デバッグ用：top_genresの内容をログに出力
        logger.info(f"User: {request.user.username}, Top Genres: {my_music_taste.top_genres}")
    
        # 自分以外のユーザーを取得
        other_users = User.objects.exclude(id=request.user.id)
        
        # 音楽の相性を計算
        compatibility_scores = []
        for other_user in other_users:
            other_music_taste, _ = MusicTaste.objects.get_or_create(user=other_user)
            score = request.user.profile.get_music_compatibility(other_user.profile)
            compatibility_scores.append({
                'user': other_user,
                'score': score,
                'common_genres': set(my_music_taste.top_genres.keys()) & set(other_music_taste.top_genres.keys())
            })
        
        return render(request, 'core/music_compatibility.html', {
            'compatibility_scores': compatibility_scores
        })
    except Exception as e:
        logger.error(f"音楽の相性計算中にエラーが発生: {str(e)}")
        return render(request, 'core/music_compatibility.html', {
            'error': '音楽の相性の計算中にエラーが発生しました。'
        })

@login_required
def popular_artists(request):
    """人気のアーティストを取得するエンドポイント"""
    try:
        page = int(request.GET.get('page', 1))
        per_page = 10
        offset = (page - 1) * per_page
        
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        # 日本の人気アーティストを取得（オフセットを使用して新しいアーティストを取得）
        results = spotify.search(
            q='genre:j-pop', 
            type='artist', 
            market='JP', 
            limit=per_page,
            offset=offset
        )
        
        artists = [{
            'name': artist['name'],
            'id': artist['id'],
            'image': artist['images'][0]['url'] if artist['images'] else None,
            'popularity': artist['popularity']
        } for artist in results['artists']['items']]
        
        # 人気度でソート
        artists.sort(key=lambda x: x['popularity'], reverse=True)
        
        return JsonResponse({
            'artists': artists,
            'has_more': len(artists) == per_page  # 取得件数が per_page と同じなら、まだデータがある
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def recommended_artists(request):
    """ユーザーにおすすめのアーティストを取得するエンドポイント"""
    try:
        page = int(request.GET.get('page', 1))
        per_page = 10
        offset = (page - 1) * per_page
        
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        # ユーザーの好みのジャンルを取得
        user_genres = list(request.user.music_taste.top_genres.keys()) if hasattr(request.user, 'music_taste') else []
        
        if user_genres:
            # ユーザーのジャンルに基づいて検索
            genre = user_genres[offset % len(user_genres)]  # ジャンルを循環させる
            results = spotify.search(
                q=f'genre:{genre}', 
                type='artist', 
                limit=per_page,
                offset=offset
            )
        else:
            # ジャンルがない場合は一般的な人気アーティストを検索
            results = spotify.search(
                q='year:2024', 
                type='artist', 
                limit=per_page,
                offset=offset
            )
        
        artists = [{
            'name': artist['name'],
            'id': artist['id'],
            'image': artist['images'][0]['url'] if artist['images'] else None
        } for artist in results['artists']['items']]
        
        return JsonResponse({
            'artists': artists,
            'has_more': len(artists) == per_page  # 取得件数が per_page と同じなら、まだデータがある
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def spotify_connect(request):
    """Spotifyとの連携を開始"""
    sp_oauth = SpotifyOAuth(
        client_id=settings.SPOTIFY_CLIENT_ID,
        client_secret=settings.SPOTIFY_CLIENT_SECRET,
        redirect_uri=settings.SPOTIFY_REDIRECT_URI,
        scope='user-read-recently-played user-top-read'
    )
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

@login_required
def spotify_callback(request):
    try:
        sp_oauth = get_spotify_oauth()
        code = request.GET.get('code')
        if not code:
            messages.error(request, 'Spotifyの認証に失敗しました。')
            return redirect('core:home')

        # アクセストークンを取得
        token_info = sp_oauth.get_access_token(code, check_cache=False)
        if not token_info:
            messages.error(request, 'Spotifyのトークン取得に失敗しました。')
            return redirect('core:home')

        # プロフィールを取得または作成
        profile = Profile.objects.get_or_create(user=request.user)[0]
        profile.spotify_refresh_token = token_info['refresh_token']
        profile.spotify_connected = True  # この行を追加
        profile.save()

        # ログ出力を追加
        logger.info(f"Spotify連携成功: user={request.user.username}, refresh_token={profile.spotify_refresh_token[:10]}...")

        messages.success(request, 'Spotifyと連携しました。')
        return redirect('core:home')

    except Exception as e:
        logger.error(f"Spotify連携エラー: {str(e)}")
        messages.error(request, f'エラーが発生しました: {str(e)}')
        return redirect('core:home')

@login_required
def spotify_disconnect(request):
    """Spotifyとの連携を解除"""
    request.user.profile.spotify_refresh_token = None
    request.user.profile.spotify_connected = False
    request.user.profile.save()
    messages.success(request, 'Spotifyとの連携を解除しました。')
    return redirect('core:profile', username=request.user.username)

@login_required
def filter_posts(request):
    """投稿をフィルタリングするビュー"""
    try:
        filter_type = request.GET.get('filter', 'all')
        sort_by = request.GET.get('sort', 'recommended')
        
        # 基本のクエリセット
        posts = MusicPost.objects.select_related('user', 'user__profile').prefetch_related('likes', 'comments').filter(
            user__isnull=False,
            user__username__isnull=False
        )
        
        # フィルタリング
        if filter_type == 'following' and request.user.is_authenticated:
            following_users = request.user.profile.following.values_list('user', flat=True)
            posts = posts.filter(user__in=following_users)
        
        if filter_type == 'today':
            japan_tz = pytz.timezone('Asia/Tokyo')
            today = timezone.now().astimezone(japan_tz).date()
            posts = posts.filter(created_at__date=today)
        
        # ソート
        if sort_by == 'newest':
            posts = posts.order_by('-created_at')
        elif sort_by == 'popular':
            posts = posts.annotate(
                like_count=Count('likes'),
                comment_count=Count('comments'),
                engagement_score=Count('likes') + (Count('comments') * 3)  # コメントの重みを3倍に
            ).order_by('-engagement_score', '-created_at')
        else:  # recommended
            if request.user.is_authenticated:
                posts = posts.annotate(
                    like_count=Count('likes'),
                    comment_count=Count('comments'),
                    is_followed=Exists(
                        Profile.objects.filter(
                            user=OuterRef('user'),
                            followers=request.user.profile
                        )
                    )
                ).annotate(
                    score=Case(
                        When(is_followed=True, then=10),
                        default=0,
                        output_field=IntegerField(),
                    ) + F('like_count') + (F('comment_count') * 3)  # コメントの重みを3倍に
                ).order_by('-score', '-created_at')
            else:
                posts = posts.annotate(
                    like_count=Count('likes'),
                    comment_count=Count('comments'),
                    engagement_score=Count('likes') + (Count('comments') * 3)  # コメントの重みを3倍に
                ).order_by('-engagement_score', '-created_at')

        # テンプレートをレンダリング
        html = render_to_string('core/includes/post_list.html', {'posts': posts}, request=request)
        return JsonResponse({
            'status': 'success',
            'html': html
        })
    except Exception as e:
        logger.error(f"投稿のフィルタリングエラー: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': '投稿の読み込みに失敗しました。'
        }, status=500)

@login_required
def create_story(request):
    """ストーリー作成エンドポイント"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            logger.info(f"ストーリー作成リクエスト: {data}")  # デバッグログ
            
            # 必須フィールドの確認
            if not data.get('spotify_track_id'):
                return JsonResponse({'status': 'error', 'message': '曲の選択は必須です'}, status=400)
            if not data.get('mood'):
                return JsonResponse({'status': 'error', 'message': '気分の選択は必須です'}, status=400)
            
            # Spotifyから曲の情報を取得
            spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
                client_id=settings.SPOTIFY_CLIENT_ID,
                client_secret=settings.SPOTIFY_CLIENT_SECRET
            ))
            track_info = spotify.track(data['spotify_track_id'])
            
            # 気分に応じたテキストを設定
            mood_text = {
                'happy': 'ハッピー',
                'chill': 'リラックス',
                'energetic': 'エネルギッシュ',
                'sad': 'メランコリー',
                'love': 'ラブ'
            }.get(data['mood'], '')
            
            # ストーリーの作成
            story = MusicStory.objects.create(
                user=request.user,
                spotify_track_id=data['spotify_track_id'],
                mood=data['mood'],
                mood_emoji=mood_text,
                comment=data.get('comment', ''),
                expires_at=timezone.now() + timezone.timedelta(hours=24)
            )
            
            logger.info(f"ストーリー作成成功: id={story.id}")  # デバッグログ
            return JsonResponse({'status': 'success', 'story_id': story.id})
            
        except json.JSONDecodeError:
            logger.error("JSONデコードエラー")
            return JsonResponse({'status': 'error', 'message': '無効なJSONデータです'}, status=400)
        except Exception as e:
            logger.error(f"ストーリー作成エラー: {str(e)}")
            return JsonResponse({'status': 'error', 'message': 'ストーリーの作成中にエラーが発生しました'}, status=500)
    
    return JsonResponse({'status': 'error', 'message': '無効なリクエストです'}, status=400)

@login_required
def story_reaction(request, story_id):
    if request.method == 'POST':
        story = get_object_or_404(MusicStory, id=story_id)
        data = json.loads(request.body)
        emoji = data.get('emoji')
        
        if emoji:
            reactions = story.quick_reactions
            reactions[emoji] = reactions.get(emoji, 0) + 1
            story.quick_reactions = reactions
            story.save()
            
            return JsonResponse({
                'status': 'success',
                'reactions': story.quick_reactions
            })
    
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def view_story(request, story_id):
    story = get_object_or_404(MusicStory, id=story_id)
    if request.user not in story.viewers.all():
        story.viewers.add(request.user)
    return JsonResponse({'status': 'success'})

@login_required
def search_track(request):
    """曲を検索するAPI"""
    query = request.GET.get('q', '')
    if not query:
        return JsonResponse({'tracks': []})
    
    try:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        results = spotify.search(q=query, type='track', market='JP', limit=5)
        tracks = [{
            'id': track['id'],
            'name': track['name'],
            'artist': track['artists'][0]['name'],
            'image': track['album']['images'][0]['url'] if track['album']['images'] else None,
            'preview_url': track['preview_url']
        } for track in results['tracks']['items']]
        
        return JsonResponse({'tracks': tracks})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def get_recently_played_tracks(spotify_client):
    """
    ユーザーの最近再生した曲を取得する
    """
    try:
        results = spotify_client.current_user_recently_played(limit=20)  # より多くの曲を取得
        tracks = []
        seen_ids = set()  # 重複チェック用のセット
        
        for item in results['items']:
            track = item['track']
            track_id = track['id']
            
            # まだ追加していない曲のみを追加
            if track_id not in seen_ids:
                seen_ids.add(track_id)
            tracks.append({
                'name': track['name'],
                'artist': track['artists'][0]['name'],
                'image': track['album']['images'][0]['url'] if track['album']['images'] else None,
                'spotify_url': track['external_urls']['spotify'],
                    'played_at': item['played_at'],
                    'spotify_id': track_id
            })
                
            # 10曲集まったら終了
            if len(tracks) >= 10:
                break
                    
        return tracks
    except Exception as e:
        logger.error(f"最近再生した曲の取得に失敗: {str(e)}")
        return []

def get_top_tracks(spotify_client):
    """
    ユーザーのトップトラックを取得する
    """
    try:
        results = spotify_client.current_user_top_tracks(limit=20, time_range='short_term')  # より多くの曲を取得
        tracks = []
        seen_ids = set()  # 重複チェック用のセット
        
        for track in results['items']:
            track_id = track['id']
            
            # まだ追加していない曲のみを追加
            if track_id not in seen_ids:
                seen_ids.add(track_id)
            tracks.append({
                'name': track['name'],
                'artist': track['artists'][0]['name'],
                'image': track['album']['images'][0]['url'] if track['album']['images'] else None,
                    'spotify_url': track['external_urls']['spotify'],
                    'spotify_id': track_id
            })
                
                # 10曲集まったら終了
            if len(tracks) >= 10:
                break
                    
        return tracks
    except Exception as e:
        logger.error(f"トップトラックの取得に失敗: {str(e)}")
        return []

@login_required
def search_track_for_story(request):
    """ストーリー作成用の曲検索エンドポイント"""
    query = request.GET.get('q', '')
    if not query:
        return JsonResponse({'tracks': []})
    
    try:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        results = spotify.search(q=query, type='track', limit=5)
        tracks = results['tracks']['items']
        
        formatted_tracks = []
        for track in tracks:
            track_data = {
                'id': track['id'],
                'title': track['name'],
                'artist': track['artists'][0]['name'],
                'imageUrl': track['album']['images'][0]['url'] if track['album']['images'] else '',
            }
            formatted_tracks.append(track_data)
        
        return JsonResponse({'tracks': formatted_tracks})
    
    except Exception as e:
        logger.error(f"楽曲検索中にエラーが発生: {str(e)}")
        return JsonResponse({'error': '楽曲の検索中にエラーが発生しました。'}, status=500)

@login_required
def get_story_details(request, story_id):
    """ストーリーの詳細情報を取得するエンドポイント"""
    try:
        story = get_object_or_404(MusicStory, id=story_id)
        
        # ストーリーを閲覧済みとしてマーク
        if request.user not in story.viewers.all():
            story.viewers.add(request.user)
        
        # 前後のストーリーを取得
        user_stories = MusicStory.objects.filter(
            user=story.user,
            expires_at__gt=timezone.now()
        ).order_by('created_at')
        
        story_ids = list(user_stories.values_list('id', flat=True))
        current_index = story_ids.index(story.id)
        
        prev_story_id = story_ids[current_index - 1] if current_index > 0 else None
        next_story_id = story_ids[current_index + 1] if current_index < len(story_ids) - 1 else None
        
        # レスポンスデータの作成
        data = {
            'id': story.id,
            'user': {
                'username': story.user.username,
                'avatar_url': story.user.profile.avatar.url if story.user.profile.avatar else '/static/images/default-avatar.svg',
            },
            'track_name': story.track_name or '',
            'artist_name': story.artist_name or '',
            'album_image_url': story.album_image_url or '',
            'spotify_track_id': story.spotify_track_id or '',
            'mood': story.mood or '',
            'mood_emoji': story.mood_emoji or '',
            'comment': story.comment or '',
            'created_at': story.created_at.isoformat(),
            'expires_at': story.expires_at.isoformat(),
            'viewers_count': story.viewers.count(),
            'prev_story_id': prev_story_id,
            'next_story_id': next_story_id,
            'is_own_story': 'true' if request.user == story.user else 'false'  # JavaScriptのブーリアン値として文字列を使用
        }
        
        return JsonResponse({'status': 'success', 'story': data})
        
    except Exception as e:
        logger.error(f"ストーリー詳細の取得に失敗: {str(e)}")
        return JsonResponse({'status': 'error', 'message': 'ストーリーの取得に失敗しました'}, status=500)

@login_required
def spotify_search(request, search_type):
    """Spotifyで曲、アーティスト、アルバムを検索"""
    query = request.GET.get('q', '')
    if not query:
        return JsonResponse({'error': '検索クエリが必要です'}, status=400)

    try:
        sp_oauth = get_spotify_oauth()
        sp = spotipy.Spotify(auth_manager=sp_oauth)

        results = {}
        
        if search_type == 'track':
            # 曲検索
            track_results = sp.search(q=query, type='track', limit=10, market='JP')
            results['tracks'] = [{
                'id': track['id'],
                'title': track['name'],
                'artist': track['artists'][0]['name'],
                'imageUrl': track['album']['images'][0]['url'] if track['album']['images'] else '',
                'preview_url': track['preview_url']
            } for track in track_results['tracks']['items']]

        elif search_type == 'artist':
            # アーティスト検索
            artist_results = sp.search(q=query, type='artist', limit=10, market='JP')
            results['artists'] = []
            for artist in artist_results['artists']['items']:
                # アーティストのトップトラックを取得
                top_tracks = sp.artist_top_tracks(artist['id'], country='JP')
                preview_track = next((track for track in top_tracks['tracks'] if track['preview_url']), None)
                
                results['artists'].append({
                    'id': artist['id'],
                    'name': artist['name'],
                    'genres': artist['genres'][:3] if artist['genres'] else [],
                    'imageUrl': artist['images'][0]['url'] if artist['images'] else '',
                    'followers': artist['followers']['total'],
                    'popularity': artist['popularity'],
                    'preview_track': {
                        'name': preview_track['name'],
                        'preview_url': preview_track['preview_url']
                    } if preview_track else None,
                    'external_url': artist['external_urls']['spotify'] if 'external_urls' in artist else None
                })

        elif search_type == 'album':
            # アルバム検索
            album_results = sp.search(q=query, type='album', limit=10, market='JP')
            results['albums'] = []
            for album in album_results['albums']['items']:
                # アルバムの詳細情報を取得
                album_info = sp.album(album['id'])
                # プレビュー可能な最初のトラックを探す
                preview_track = next((track for track in album_info['tracks']['items'] if track.get('preview_url')), None)
                
                results['albums'].append({
                    'id': album['id'],
                    'name': album['name'],
                    'artist': album['artists'][0]['name'],
                    'imageUrl': album['images'][0]['url'] if album['images'] else '',
                    'release_date': album['release_date'],
                    'total_tracks': album['total_tracks'],
                    'preview_track': {
                        'name': preview_track['name'],
                        'preview_url': preview_track['preview_url']
                    } if preview_track else None,
                    'external_url': album['external_urls']['spotify'] if 'external_urls' in album else None
                })

        return JsonResponse(results)

    except Exception as e:
        logger.error(f"Spotify検索エラー: {str(e)}")
        return JsonResponse({'error': '検索中にエラーが発生しました'}, status=500)

@login_required
def story_detail(request, pk):
    """ストーリーの詳細を表示"""
    story = get_object_or_404(MusicStory, pk=pk)
    
    # ストーリーが期限切れの場合
    if story.is_expired:
        messages.error(request, 'このストーリーは期限切れです。')
        return redirect('core:home')
    
    # 非公開ストーリーの場合、作成者のみアクセス可能
    if not story.is_public and story.user != request.user:
        messages.error(request, 'このストーリーにはアクセスできません。')
        return redirect('core:home')
    
    # 閲覧履歴を記録
    if request.user not in story.viewers.all():
        story.viewers.add(request.user)
    
    # 前後のストーリーを取得
    user_stories = MusicStory.objects.filter(
        user=story.user,
        expires_at__gt=timezone.now()
    ).order_by('created_at')
    
    story_ids = list(user_stories.values_list('id', flat=True))
    current_index = story_ids.index(story.id)
    
    context = {
        'story': story,
        'prev_story_id': story_ids[current_index - 1] if current_index > 0 else None,
        'next_story_id': story_ids[current_index + 1] if current_index < len(story_ids) - 1 else None,
        'viewers_count': story.viewers.count(),
        'is_own_story': request.user == story.user
    }
    
    return render(request, 'core/story_detail.html', context)

@login_required
def delete_story(request, pk):
    """ストーリーの削除"""
    story = get_object_or_404(MusicStory, pk=pk, user=request.user)
    
    if request.method == 'POST':
        story.delete()
        messages.success(request, 'ストーリーを削除しました。')
        return redirect('core:home')
    
    return render(request, 'core/story_confirm_delete.html', {'story': story})

@login_required
def like_playlist(request, playlist_id):
    """プレイリストのいいね処理"""
    try:
        playlist = get_object_or_404(Playlist, id=playlist_id)
        
        if request.user in playlist.likes.all():
            playlist.likes.remove(request.user)
            liked = False
        else:
            playlist.likes.add(request.user)
            liked = True
            # 自分の投稿以外の場合は通知を作成
            if request.user != playlist.user:
                Notification.objects.create(
                    recipient=playlist.user,
                    sender=request.user,
                    notification_type='like',
                    playlist=playlist
                )
        
        return JsonResponse({
            'status': 'success',
            'liked': liked,
            'like_count': playlist.likes.count()
        })
    except Exception as e:
        logger.error(f"プレイリストのいいね処理中にエラーが発生: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'いいねの処理中にエラーが発生しました'
        }, status=500)

@login_required
def add_playlist_comment(request, playlist_id):
    """プレイリストへのコメント追加"""
    playlist = get_object_or_404(Playlist, id=playlist_id)
    
    if request.method == 'POST':
        try:
            content = request.POST.get('content')
            if not content:
                return JsonResponse({
                    'status': 'error',
                    'message': 'コメント内容を入力してください'
                }, status=400)
            
            comment = PlaylistComment.objects.create(
                playlist=playlist,
                user=request.user,
                content=content
            )
            
            # 自分の投稿以外の場合は通知を作成
            if request.user != playlist.user:
                Notification.objects.create(
                    recipient=playlist.user,
                    sender=request.user,
                    notification_type='comment',
                    playlist=playlist,
                    comment=comment
                )
            
            # コメントのHTMLをレンダリング
            html = render_to_string('core/includes/playlist_comment.html', {
                'comment': comment
            }, request=request)
            
            return JsonResponse({
                'status': 'success',
                'html': html,
                'comment_count': playlist.playlist_comments.count()
            })
            
        except Exception as e:
            logger.error(f"プレイリストへのコメント追加中にエラーが発生: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': 'コメントの追加中にエラーが発生しました'
            }, status=500)
    
    return JsonResponse({'status': 'error', 'message': '無効なリクエストです'}, status=400)

def get_recommended_playlists():
    """おすすめのプレイリストを取得"""
    # 過去1週間の人気プレイリストを取得
    week_ago = timezone.now() - timezone.timedelta(days=7)
    popular_playlists = Playlist.objects.filter(
        is_public=True,
        created_at__gte=week_ago
    ).annotate(
        engagement_score=Count('likes') + Count('playlist_comments') * 2
    ).order_by('-engagement_score')[:5]
    
    return popular_playlists

@login_required
def add_comment(request, post_id):
    """投稿へのコメント追加"""
    try:
        post = get_object_or_404(MusicPost, id=post_id)
        
        if request.method == 'POST':
            data = json.loads(request.body)
            content = data.get('content')
            
            if not content:
                return JsonResponse({
                    'status': 'error',
                    'message': 'コメント内容を入力してください'
                }, status=400)
            
            comment = Comment.objects.create(
                post=post,
                user=request.user,
                content=content
            )
            
            # 自分の投稿以外の場合は通知を作成
            if request.user != post.user:
                Notification.objects.create(
                    recipient=post.user,
                    sender=request.user,
                    notification_type='comment',
                    post=post,
                    comment=comment
                )
            
            return JsonResponse({
                'status': 'success',
                'comment': {
                    'username': comment.user.username,
                    'avatar_url': comment.user.profile.avatar.url if comment.user.profile.avatar else '/static/images/default-avatar.svg',
                    'content': comment.content,
                    'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M:%S')
                }
            })
            
    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': '無効なJSONデータです'
        }, status=400)
    except Exception as e:
        logger.error(f"コメント追加中にエラーが発生: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'コメントの追加中にエラーが発生しました'
        }, status=500)

    return JsonResponse({'status': 'error', 'message': '無効なリクエストです'}, status=400)

@login_required
def get_artist_analysis(request):
    """アーティスト詳細分析のデータを取得するAPI"""
    try:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        # ユーザーの好みのアーティストを取得
        user_artists = request.user.music_taste.favorite_artists if hasattr(request.user, 'music_taste') else []
        
        if not user_artists:
            return JsonResponse({
                'error': 'アーティストデータがありません。音楽の好みを設定してください。'
            }, status=404)
        
        # アーティスト情報を取得
        artists_data = []
        for artist_name in user_artists[:5]:  # 上位5アーティスト
            results = spotify.search(q=artist_name, type='artist', limit=1)
            if results['artists']['items']:
                artist = results['artists']['items'][0]
                artists_data.append({
                    'name': artist['name'],
                    'popularity': artist['popularity'],
                    'genres': artist['genres'],
                    'followers': artist['followers']['total']
                })
        
        # ジャンル分布データ
        genre_counts = {}
        for artist in artists_data:
            for genre in artist['genres']:
                genre_counts[genre] = genre_counts.get(genre, 0) + 1
        
        # アーティスト相関データ
        artist_correlation = [
            {
                'x': artist['popularity'],
                'y': artist['followers'] / 10000,  # フォロワー数を正規化
                'r': len(artist['genres']) * 5,  # ジャンル数に基づくバブルサイズ
                'label': artist['name']
            }
            for artist in artists_data
        ]
        
        # トレンドデータ（週間）
        trend_data = {
            'labels': ['月', '火', '水', '木', '金', '土', '日'],
            'data': [random.randint(50, 100) for _ in range(7)]  # ダミーデータ
        }
        
        return JsonResponse({
            'genre_data': {
                'labels': list(genre_counts.keys()),
                'data': list(genre_counts.values())
            },
            'artist_correlation': artist_correlation,
            'trend_data': trend_data
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_mood_recommendations(request, mood_id):
    """ムード別のおすすめプレイリストを取得するAPI"""
    try:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        # ムードに基づく検索クエリのマッピング
        mood_queries = {
            'energetic': 'energy:0.8',
            'relax': 'energy:0.3',
            'focus': 'instrumentalness:0.8',
            'party': 'danceability:0.8'
        }
        
        query = mood_queries.get(mood_id, 'energy:0.5')
        results = spotify.search(
            q=f'{query} year:2024', 
            type='track', 
            market='JP', 
            limit=10
        )
        
        tracks = [{
            'title': track['name'],
            'artist': track['artists'][0]['name'],
            'album_cover': track['album']['images'][0]['url'] if track['album']['images'] else None,
            'preview_url': track['preview_url'],
            'duration': track['duration_ms'] // 1000,  # ミリ秒から秒に変換
            'mood_id': mood_id
        } for track in results['tracks']['items']]
        
        return JsonResponse({'tracks': tracks})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def create_story_modal(request):
    """ストーリー作成モーダルを表示するビュー"""
    return render(request, 'core/create_story_modal.html')

@login_required
def messages_view(request):
    """メッセージ一覧を表示するビュー"""
    conversations = request.user.conversations.all().prefetch_related('participants')
    
    # 各会話の情報を準備
    conversations_data = []
    for conversation in conversations:
        # 会話の相手を取得
        other_user = conversation.participants.exclude(id=request.user.id).first()
        
        # 未読メッセージ数を取得
        unread_count = Message.objects.filter(
            sender=other_user,
            recipient=request.user,
            is_read=False
        ).count()
        
        conversations_data.append({
            'conversation': conversation,
            'other_user': other_user,
            'unread_count': unread_count,
            'last_message': conversation.last_message
        })
    
    return render(request, 'core/messages.html', {
        'conversations_data': conversations_data
    })

@login_required
def conversation_detail(request, conversation_id):
    """特定の会話の詳細を表示するビュー"""
    conversation = get_object_or_404(Conversation, id=conversation_id, participants=request.user)
    other_user = conversation.participants.exclude(id=request.user.id).first()
    
    # この会話の未読メッセージを既読にする
    Message.objects.filter(
        sender=other_user,
        recipient=request.user,
        is_read=False
    ).update(is_read=True)
    
    # 全ての会話を取得（サイドバー用）
    all_conversations = []
    for conv in request.user.conversations.all():
        conv_other_user = conv.participants.exclude(id=request.user.id).first()
        all_conversations.append({
            'conversation': conv,
            'other_user': conv_other_user,
            'is_active': conv.id == conversation_id,
            'last_message': conv.last_message
        })
    
    messages = Message.objects.filter(
        sender__in=conversation.participants.all(),
        recipient__in=conversation.participants.all()
    ).order_by('created_at')
    
    return render(request, 'core/conversation_detail.html', {
        'conversation': conversation,
        'messages': messages,
        'other_user': other_user,
        'all_conversations': all_conversations
    })

@login_required
def new_conversation(request, username):
    """新しい会話を開始するビュー"""
    other_user = get_object_or_404(User, username=username)
    
    # 既存の会話を探す
    existing_conversation = Conversation.objects.filter(
        participants=request.user
    ).filter(
        participants=other_user
    ).first()
    
    if existing_conversation:
        return redirect('core:conversation_detail', conversation_id=existing_conversation.id)
    
    # 新しい会話を作成
    conversation = Conversation.objects.create()
    conversation.participants.add(request.user, other_user)
    
    return redirect('core:conversation_detail', conversation_id=conversation.id)

@login_required
def send_message(request):
    """メッセージを送信するAPI"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            conversation_id = data.get('conversation_id')
            content = data.get('content')
            
            if not content:
                return JsonResponse({'error': 'メッセージを入力してください'}, status=400)
            
            conversation = get_object_or_404(Conversation, id=conversation_id, participants=request.user)
            recipient = conversation.participants.exclude(id=request.user.id).first()
            
            message = Message.objects.create(
                sender=request.user,
                recipient=recipient,
                content=content
            )
            
            conversation.last_message = message
            conversation.save()
            
            return JsonResponse({
                'status': 'success',
                'message': {
                    'id': message.id,
                    'content': message.content,
                    'created_at': message.created_at.isoformat(),
                    'sender_username': message.sender.username,
                    'sender_avatar': message.sender.profile.avatar.url if message.sender.profile.avatar else None
                }
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': '無効なリクエストです'}, status=400)

@login_required
def get_unread_messages_count(request):
    """未読メッセージの総数を取得するAPI"""
    count = Message.objects.filter(
        recipient=request.user,
        is_read=False
    ).count()
    return JsonResponse({'count': count})

@login_required
def toggle_follow(request, username):
    if request.method == 'POST':
        try:
            target_user = User.objects.get(username=username)
            user_profile = request.user.profile
            target_profile = target_user.profile

            if target_profile in user_profile.following.all():
                # フォロー解除
                user_profile.following.remove(target_profile)
                status = 'unfollowed'
            else:
                # フォロー
                user_profile.following.add(target_profile)
                status = 'followed'

            # フォロワー数を取得（target_userをフォローしているユーザー数）
            follower_count = Profile.objects.filter(following=target_profile).count()

            return JsonResponse({
                'status': status,
                'follower_count': follower_count
            })
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def get_post_likes(request, post_id):
    try:
        post = get_object_or_404(MusicPost, id=post_id)
        users = post.likes.all().select_related('profile')
        users_data = [{
            'username': user.username,
            'name': user.get_full_name(),
            'avatar': user.profile.avatar.url if user.profile.avatar else None
        } for user in users]
        
        return JsonResponse({
            'status': 'success',
            'users': users_data
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': 'エラーが発生しました。'
        }, status=500)

def get_post_comments(request, post_id):
    if request.method == 'GET':
        try:
            offset = int(request.GET.get('offset', 0))
            limit = int(request.GET.get('limit', 10))
            post = MusicPost.objects.get(id=post_id)
            
            comments = post.comments.all()[offset:offset+limit]
            comments_data = [{
                'content': comment.content,
                'user': {
                    'username': comment.user.username,
                    'avatar_url': comment.user.profile.avatar.url if comment.user.profile.avatar else None
                }
            } for comment in comments]
            
            return JsonResponse({
                'status': 'success',
                'comments': comments_data
            })
        except MusicPost.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': '投稿が見つかりません。'
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    return JsonResponse({
        'status': 'error',
        'message': '無効なリクエストメソッドです。'
    }, status=405)