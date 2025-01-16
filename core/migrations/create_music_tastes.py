from django.db import migrations

def create_music_tastes(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    MusicTaste = apps.get_model('core', 'MusicTaste')
    
    for user in User.objects.all():
        MusicTaste.objects.get_or_create(user=user)

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0003_profile_favorite_artists_profile_favorite_genres_and_more'),
    ]

    operations = [
        migrations.RunPython(create_music_tastes),
    ] 