

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import simple_history.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('catalog', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Watch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True, verbose_name='name')),
                ('enabled', models.BooleanField(default=True, verbose_name='enabled')),
                ('interval_hours', models.PositiveSmallIntegerField(default=24, validators=[django.core.validators.MinValueValidator(1)], verbose_name='interval (hours)')),
                ('auto_download', models.BooleanField(default=False, verbose_name='automatic download')),
                ('next_run_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name='next check')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='created')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated')),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='HistoricalWatch',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=120, verbose_name='name')),
                ('enabled', models.BooleanField(default=True, verbose_name='enabled')),
                ('interval_hours', models.PositiveSmallIntegerField(default=24, validators=[django.core.validators.MinValueValidator(1)], verbose_name='interval (hours)')),
                ('auto_download', models.BooleanField(default=False, verbose_name='automatic download')),
                ('next_run_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name='next check')),
                ('created_at', models.DateTimeField(blank=True, editable=False, verbose_name='created')),
                ('updated_at', models.DateTimeField(blank=True, editable=False, verbose_name='updated')),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical watch',
                'verbose_name_plural': 'historical watchs',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='WatchArtist',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('position', models.PositiveSmallIntegerField(default=0, verbose_name='position')),
                ('artist', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='watch_entries', to='catalog.artist')),
                ('watch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='watch_artists', to='watches.watch')),
            ],
            options={
                'ordering': ['watch', 'position'],
            },
        ),
        migrations.AddField(
            model_name='watch',
            name='artists',
            field=models.ManyToManyField(related_name='watches', through='watches.WatchArtist', to='catalog.artist', verbose_name='artists'),
        ),
        migrations.CreateModel(
            name='WatchRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('started_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='started')),
                ('finished_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='finished')),
                ('status', models.CharField(choices=[('succeeded', 'succeeded'), ('failed', 'failed')], max_length=10, verbose_name='status')),
                ('found', models.PositiveIntegerField(default=0, verbose_name='new releases found')),
                ('detail', models.TextField(blank=True, verbose_name='detail')),
                ('watch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='runs', to='watches.watch', verbose_name='watch')),
            ],
            options={
                'ordering': ['-finished_at', '-id'],
            },
        ),
        migrations.AddConstraint(
            model_name='watchartist',
            constraint=models.UniqueConstraint(fields=('watch', 'artist'), name='unique_watch_artist'),
        ),
    ]
