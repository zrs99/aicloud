# Generated by Django 5.1.6 on 2025-03-24 07:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("blogs", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="uploadedfile",
            name="file",
            field=models.FileField(upload_to="blogs/uploads/"),
        ),
        migrations.AlterField(
            model_name="uploadedfile",
            name="title",
            field=models.CharField(max_length=300),
        ),
    ]
