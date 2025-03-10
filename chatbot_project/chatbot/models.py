from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission

# Custom User Model


# User Model (Separate from Authentication Model)
class User(models.Model):
    full_name = models.CharField(max_length=255)
    username = models.CharField(max_length=255, unique=True)  # Prevent duplicate usernames
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)  # Consider hashing passwords
    address = models.TextField()
    phone = models.CharField(max_length=20)

    def __str__(self):
        return self.full_name
