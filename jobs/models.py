from django.db import models
from candidate.models import Candidate

class Jobs(models.Model):
    title = models.CharField(max_length=255)
    company = models.CharField(max_length=255)
    location = models.CharField(max_length=100)
    description = models.TextField()
    requirements = models.TextField()
    posted_date = models.DateField()
    expiration_date = models.DateField()
    contact_information = models.TextField(blank=True, null=True)

    def __str__(self) -> str:
        return self.title()
