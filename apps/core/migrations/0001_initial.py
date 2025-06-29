# Generated by Django 5.2.3 on 2025-06-20 10:10

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='RegulatoryEntity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('description', models.TextField(blank=True)),
                ('color', models.CharField(default='#007bff', max_length=7)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Entité Réglementaire',
                'verbose_name_plural': 'Entités Réglementaires',
            },
        ),
    ]
