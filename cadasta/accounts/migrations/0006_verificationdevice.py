# -*- coding: utf-8 -*-
# Generated by Django 1.10.7 on 2017-06-19 17:07
from __future__ import unicode_literals

import accounts.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django_otp.util


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_auto_20170619_1655'),
    ]

    operations = [
        migrations.CreateModel(
            name='VerificationDevice',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='The human-readable name of this device.', max_length=64)),
                ('confirmed', models.BooleanField(default=True, help_text='Is this device ready for use?')),
                ('unverified_phone', models.CharField(blank=True, max_length=16)),
                ('secret_key', models.CharField(default=accounts.models.default_key, help_text='Hex-encoded secret key to generate totp tokens.', max_length=40, unique=True, validators=[django_otp.util.hex_validator])),
                ('last_t', models.BigIntegerField(default=-1, help_text='The t value of the latest verified token.         The next token must be at a higher time step.         It makes sure a token is used only once.')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Verification Device',
                'abstract': False,
            },
        ),
    ]