# Generated by Django 5.0 on 2025-01-16 07:31

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_notification'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='comment',
            options={},
        ),
        migrations.AlterModelOptions(
            name='musicstory',
            options={'ordering': ['-created_at']},
        ),
        migrations.AlterModelOptions(
            name='playlist',
            options={},
        ),
        migrations.RemoveField(
            model_name='comment',
            name='updated_at',
        ),
        migrations.RemoveField(
            model_name='musicpost',
            name='updated_at',
        ),
        migrations.RemoveField(
            model_name='musicstory',
            name='spotify_link',
        ),
        migrations.RemoveField(
            model_name='notification',
            name='story',
        ),
        migrations.RemoveField(
            model_name='playlist',
            name='image',
        ),
        migrations.RemoveField(
            model_name='profile',
            name='following',
        ),
        migrations.RemoveField(
            model_name='profile',
            name='image',
        ),
        migrations.AddField(
            model_name='musicpost',
            name='listening_context',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='musicpost',
            name='location',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='musicpost',
            name='recommended_for',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='musicpost',
            name='related_artists',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='musicpost',
            name='scheduled_time',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='musicstory',
            name='album_art',
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='musicstory',
            name='mood_emoji',
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
        migrations.AddField(
            model_name='musicstory',
            name='preview_url',
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='musicstory',
            name='spotify_track_id',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='avatar',
            field=models.ImageField(blank=True, null=True, upload_to='avatars/'),
        ),
        migrations.AddField(
            model_name='profile',
            name='followers',
            field=models.ManyToManyField(blank=True, related_name='following', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='profile',
            name='music_mood_preferences',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='profile',
            name='nickname',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AlterField(
            model_name='musicpost',
            name='artist',
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name='musicpost',
            name='description',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='musicpost',
            name='spotify_link',
            field=models.CharField(max_length=200),
        ),
        migrations.AlterField(
            model_name='musicpost',
            name='title',
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name='musicpost',
            name='youtube_link',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AlterField(
            model_name='musicstory',
            name='artist',
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name='musicstory',
            name='comment',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='musicstory',
            name='mood',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name='musicstory',
            name='title',
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name='musicstory',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stories', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(choices=[('like', 'いいね'), ('comment', 'コメント'), ('follow', 'フォロー')], max_length=20),
        ),
        migrations.AlterField(
            model_name='profile',
            name='favorite_artists',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='profile',
            name='favorite_genres',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='profile',
            name='spotify_refresh_token',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='profile',
            name='website',
            field=models.URLField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='MusicTaste',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('genres', models.JSONField(blank=True, default=dict)),
                ('moods', models.JSONField(blank=True, default=dict)),
                ('spotify_genres', models.JSONField(blank=True, default=list)),
                ('favorite_artists', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='music_taste', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='StoryView',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('viewed_at', models.DateTimeField(auto_now_add=True)),
                ('story', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='views', to='core.musicstory')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('story', 'user')},
            },
        ),
    ]
