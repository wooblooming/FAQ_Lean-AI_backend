# Generated by Django 5.0.7 on 2024-10-18 00:06

import faq.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faq', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='menu',
            options={},
        ),
        migrations.RemoveField(
            model_name='menu',
            name='menu_id',
        ),
        migrations.AlterField(
            model_name='edit',
            name='file',
            field=models.FileField(blank=True, null=True, upload_to=faq.models.user_directory_path),
        ),
        migrations.AlterField(
            model_name='menu',
            name='menu_number',
            field=models.PositiveIntegerField(default=1, primary_key=True, serialize=False),
        ),
    ]