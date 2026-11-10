

import django.db.models.deletion
import simple_history.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Album',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ytmusic_id', models.CharField(blank=True, help_text='Browse id.', max_length=64, null=True, unique=True)),
                ('title', models.CharField(db_index=True, max_length=255)),
                ('year', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('cover_url', models.URLField(blank=True, max_length=500)),
                ('record_type', models.CharField(choices=[('album', 'Album'), ('single', 'Single'), ('ep', 'EP')], default='album', max_length=20)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Download',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file_path', models.CharField(max_length=1000)),
                ('audio_format', models.CharField(max_length=10)),
                ('source_url', models.URLField(blank=True, max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Recording',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('video_id', models.CharField(blank=True, max_length=11, null=True, unique=True)),
                ('title', models.CharField(db_index=True, max_length=255)),
                ('duration', models.PositiveIntegerField(blank=True, help_text='Seconds.', null=True)),
                ('explicit', models.BooleanField(default=False)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='AlbumLoudness',
            fields=[
                ('lufs', models.FloatField(help_text='Integrated loudness (LUFS).')),
                ('peak', models.FloatField(help_text='True peak; 1 is full scale.')),
                ('album', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='loudness', serialize=False, to='catalog.album')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Artist',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ytmusic_id', models.CharField(blank=True, help_text='Channel id.', max_length=64, null=True, unique=True)),
                ('name', models.CharField(db_index=True, max_length=255)),
                ('image_url', models.URLField(blank=True, max_length=500)),
                ('description', models.TextField(blank=True)),
                ('monthly_listeners', models.PositiveBigIntegerField(blank=True, null=True)),
                ('subscribers', models.PositiveBigIntegerField(blank=True, null=True)),
                ('related', models.ManyToManyField(blank=True, related_name='related_from', to='catalog.artist')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='AlbumArtist',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('position', models.PositiveSmallIntegerField(default=0)),
                ('album', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='credits', to='catalog.album')),
                ('artist', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='album_credits', to='catalog.artist')),
            ],
            options={
                'ordering': ['album', 'position'],
            },
        ),
        migrations.AddField(
            model_name='album',
            name='artists',
            field=models.ManyToManyField(related_name='albums', through='catalog.AlbumArtist', to='catalog.artist'),
        ),
        migrations.CreateModel(
            name='BlockedItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('artist', 'Artist'), ('album', 'Album'), ('track', 'Track')], max_length=10)),
                ('external_id', models.CharField(help_text='Channel id, browse id or video id, depending on the kind.', max_length=64)),
                ('name', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('kind', 'external_id'), name='unique_blocked_item')],
            },
        ),
        migrations.CreateModel(
            name='DownloadLoudness',
            fields=[
                ('lufs', models.FloatField(help_text='Integrated loudness (LUFS).')),
                ('peak', models.FloatField(help_text='True peak; 1 is full scale.')),
                ('download', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='loudness', serialize=False, to='catalog.download')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='HistoricalAlbum',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('ytmusic_id', models.CharField(blank=True, db_index=True, help_text='Browse id.', max_length=64, null=True)),
                ('title', models.CharField(db_index=True, max_length=255)),
                ('year', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('cover_url', models.URLField(blank=True, max_length=500)),
                ('record_type', models.CharField(choices=[('album', 'Album'), ('single', 'Single'), ('ep', 'EP')], default='album', max_length=20)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical album',
                'verbose_name_plural': 'historical albums',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalAlbumArtist',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('position', models.PositiveSmallIntegerField(default=0)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('album', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='catalog.album')),
                ('artist', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='catalog.artist')),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical album artist',
                'verbose_name_plural': 'historical album artists',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalArtist',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('ytmusic_id', models.CharField(blank=True, db_index=True, help_text='Channel id.', max_length=64, null=True)),
                ('name', models.CharField(db_index=True, max_length=255)),
                ('image_url', models.URLField(blank=True, max_length=500)),
                ('description', models.TextField(blank=True)),
                ('monthly_listeners', models.PositiveBigIntegerField(blank=True, null=True)),
                ('subscribers', models.PositiveBigIntegerField(blank=True, null=True)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical artist',
                'verbose_name_plural': 'historical artists',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalBlockedItem',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('kind', models.CharField(choices=[('artist', 'Artist'), ('album', 'Album'), ('track', 'Track')], max_length=10)),
                ('external_id', models.CharField(help_text='Channel id, browse id or video id, depending on the kind.', max_length=64)),
                ('name', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(blank=True, editable=False)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical blocked item',
                'verbose_name_plural': 'historical blocked items',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalRecording',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('video_id', models.CharField(blank=True, db_index=True, max_length=11, null=True)),
                ('title', models.CharField(db_index=True, max_length=255)),
                ('duration', models.PositiveIntegerField(blank=True, help_text='Seconds.', null=True)),
                ('explicit', models.BooleanField(default=False)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical recording',
                'verbose_name_plural': 'historical recordings',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalTrack',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('title', models.CharField(db_index=True, max_length=255)),
                ('track_number', models.PositiveSmallIntegerField(default=1)),
                ('disc_number', models.PositiveSmallIntegerField(default=1)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('album', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='catalog.album')),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('recording', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='catalog.recording')),
            ],
            options={
                'verbose_name': 'historical track',
                'verbose_name_plural': 'historical tracks',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalRecordingArtist',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('position', models.PositiveSmallIntegerField(default=0)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('artist', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='catalog.artist')),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('recording', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='catalog.recording')),
            ],
            options={
                'verbose_name': 'historical recording artist',
                'verbose_name_plural': 'historical recording artists',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='RecordingArtist',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('position', models.PositiveSmallIntegerField(default=0)),
                ('artist', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recording_credits', to='catalog.artist')),
                ('recording', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='credits', to='catalog.recording')),
            ],
            options={
                'ordering': ['recording', 'position'],
            },
        ),
        migrations.AddField(
            model_name='recording',
            name='artists',
            field=models.ManyToManyField(related_name='recordings', through='catalog.RecordingArtist', to='catalog.artist'),
        ),
        migrations.CreateModel(
            name='Track',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(db_index=True, max_length=255)),
                ('track_number', models.PositiveSmallIntegerField(default=1)),
                ('disc_number', models.PositiveSmallIntegerField(default=1)),
                ('album', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tracks', to='catalog.album')),
                ('recording', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='tracks', to='catalog.recording')),
            ],
            options={
                'ordering': ['album', 'disc_number', 'track_number'],
            },
        ),
        migrations.AddField(
            model_name='download',
            name='track',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='catalog.track'),
        ),
        migrations.AddConstraint(
            model_name='albumartist',
            constraint=models.UniqueConstraint(fields=('album', 'artist'), name='unique_album_artist'),
        ),
        migrations.AddConstraint(
            model_name='recordingartist',
            constraint=models.UniqueConstraint(fields=('recording', 'artist'), name='unique_recording_artist'),
        ),
        migrations.AddConstraint(
            model_name='track',
            constraint=models.UniqueConstraint(fields=('album', 'disc_number', 'track_number'), name='unique_track_position'),
        ),
    ]
