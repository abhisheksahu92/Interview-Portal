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


class JobsExam(models.Model):
    exam_choice = (('Python', 'Python'), ('Java', 'Java'))
    job_id =  models.ForeignKey(Jobs,related_name='+',on_delete=models.CASCADE)
    exam = models.CharField(max_length=10, default='Python', choices=exam_choice, null=False, blank=False)