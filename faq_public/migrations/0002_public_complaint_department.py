# Generated by Django 5.0.7 on 2024-11-14 02:14

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faq_public', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='public_complaint',
            name='department',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, related_name='complaints', to='faq_public.public_department'),
            preserve_default=False,
        ),
    ]