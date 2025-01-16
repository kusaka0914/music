from django.db import migrations

def migrate_artists_data(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Profile = apps.get_model('core', 'Profile')
    MusicTaste = apps.get_model('core', 'MusicTaste')
    
    for user in User.objects.all():
        try:
            profile = Profile.objects.get(user=user)
            music_taste = MusicTaste.objects.get(user=user)
            
            if profile.favorite_artists:
                music_taste.favorite_artists = profile.favorite_artists
                music_taste.save()
        except (Profile.DoesNotExist, MusicTaste.DoesNotExist):
            continue

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0002_musictaste_favorite_artists'),
    ]

    operations = [
        migrations.RunPython(migrate_artists_data),
    ] 