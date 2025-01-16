from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Q
from .models import Profile, MusicPost, Comment, Playlist, Notification
from .forms import UserRegisterForm, UserUpdateForm, ProfileUpdateForm, MusicPostForm, CommentForm, PlaylistForm
from django.http import JsonResponse

def home(request):
    posts = MusicPost.objects.all().order_by('-created_at')
    return render(request, 'core/home.html', {'posts': posts})

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, 'ログインしました。')
            return redirect('core:home')
        else:
            messages.error(request, 'ユーザー名またはパスワードが正しくありません。')
    return render(request, 'core/login.html')

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
        form = MusicPostForm(request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.user = request.user
            
            # Spotifyリンクから`si=`パラメータを削除
            spotify_link = form.cleaned_data['spotify_link']
            if spotify_link:
                # まずベースURLを削除
                if 'https://open.spotify.com/intl-ja/track/' in spotify_link:
                    spotify_link = spotify_link.split('https://open.spotify.com/intl-ja/track/')[1]
                # si パラメータを削除
                if '?si=' in spotify_link:
                    spotify_link = spotify_link.split('?si=')[0]
                elif '&si=' in spotify_link:
                    spotify_link = spotify_link.split('&si=')[0]
                post.spotify_link = spotify_link
            
            post.save()
            return redirect('core:post_detail', pk=post.pk)
    else:
        form = MusicPostForm()
    return render(request, 'core/post_form.html', {'form': form})

def post_detail(request, pk):
    post = get_object_or_404(MusicPost, pk=pk)
    comments = post.comments.all().order_by('-created_at')
    return render(request, 'core/post_detail.html', {'post': post, 'comments': comments})

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
def like_post(request, pk):
    post = get_object_or_404(MusicPost, pk=pk)
    if request.user in post.likes.all():
        post.likes.remove(request.user)
        liked = False
    else:
        post.likes.add(request.user)
        liked = True
        if request.user != post.user:
            Notification.objects.create(
                recipient=post.user,
                sender=request.user,
                notification_type='like',
                post=post
            )
    return JsonResponse({'liked': liked, 'like_count': post.likes.count()})

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

def profile(request, username):
    profile_user = get_object_or_404(User, username=username)
    posts = profile_user.musicpost_set.all().order_by('-created_at')
    return render(request, 'core/profile.html', {
        'profile_user': profile_user,
        'posts': posts
    })

@login_required
def follow_user(request, username):
    user_to_follow = get_object_or_404(User, username=username)
    if request.user != user_to_follow:
        if request.user in user_to_follow.profile.followers.all():
            user_to_follow.profile.followers.remove(request.user)
            is_following = False
        else:
            user_to_follow.profile.followers.add(request.user)
            is_following = True
            Notification.objects.create(
                recipient=user_to_follow,
                sender=request.user,
                notification_type='follow'
            )
        return JsonResponse({
            'is_following': is_following,
            'followers_count': user_to_follow.profile.followers.count()
        })
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def create_playlist(request):
    if request.method == 'POST':
        form = PlaylistForm(request.POST)
        if form.is_valid():
            playlist = form.save(commit=False)
            playlist.user = request.user
            playlist.save()
            messages.success(request, 'プレイリストが作成されました。')
            return redirect('core:playlist_detail', pk=playlist.pk)
    else:
        form = PlaylistForm()
    return render(request, 'core/playlist_form.html', {'form': form, 'title': '新規プレイリスト'})

def playlist_detail(request, pk):
    playlist = get_object_or_404(Playlist, pk=pk)
    if not playlist.is_public and playlist.user != request.user:
        messages.error(request, 'このプレイリストは非公開です。')
        return redirect('core:home')
    return render(request, 'core/playlist_detail.html', {'playlist': playlist})

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
    notifications = request.user.notifications_received.all().order_by('-created_at')
    unread_count = notifications.filter(is_read=False).count()
    return render(request, 'core/notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count
    })

@login_required
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notification.is_read = True
    notification.save()
    return redirect('core:notifications')

@login_required
def following_posts(request):
    following_users = User.objects.filter(profile__followers=request.user)
    posts = MusicPost.objects.filter(user__in=following_users).order_by('-created_at')
    return render(request, 'core/following_posts.html', {'posts': posts})

def search(request):
    query = request.GET.get('q', '')
    posts = []
    if query:
        posts = MusicPost.objects.filter(
            Q(title__icontains=query) |
            Q(artist__icontains=query) |
            Q(description__icontains=query) |
            Q(user__username__icontains=query)
        ).order_by('-created_at')
    return render(request, 'core/search.html', {
        'query': query,
        'posts': posts
    })

@login_required
def profile_edit(request):
    # プロフィールが存在しない場合は作成
    Profile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = ProfileUpdateForm(request.POST, instance=request.user.profile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'プロフィールが更新されました。')
            return redirect('core:profile', username=request.user.username)
    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = ProfileUpdateForm(instance=request.user.profile)
    
    return render(request, 'core/profile_edit.html', {
        'user_form': user_form,
        'profile_form': profile_form
    })
