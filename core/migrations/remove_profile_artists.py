from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('core', 'migrate_artists_data'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='profile',
            name='favorite_artists',
        ),
    ] 