

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Proxy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.CharField(max_length=500, unique=True, verbose_name='URL')),
                ('ip_version', models.CharField(choices=[('ipv4', 'IPv4'), ('ipv6', 'IPv6')], db_default='ipv4', default='ipv4', max_length=4, verbose_name='IP version')),
                ('enabled', models.BooleanField(default=True, verbose_name='enabled')),
                ('success_count', models.PositiveIntegerField(default=0, verbose_name='successes')),
                ('failure_count', models.PositiveIntegerField(default=0, verbose_name='failures')),
                ('last_used_at', models.DateTimeField(blank=True, null=True, verbose_name='last used')),
                ('last_failed_at', models.DateTimeField(blank=True, null=True, verbose_name='last failure')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='created')),
            ],
            options={
                'ordering': ['url'],
            },
        ),
        migrations.CreateModel(
            name='ServiceIpSupport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('host', models.CharField(max_length=255, unique=True, verbose_name='host')),
                ('ipv4', models.BooleanField(verbose_name='IPv4')),
                ('ipv6', models.BooleanField(verbose_name='IPv6')),
                ('checked_at', models.DateTimeField(auto_now_add=True, verbose_name='checked')),
            ],
        ),
    ]
