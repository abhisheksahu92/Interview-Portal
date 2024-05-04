from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils.crypto import get_random_string
from jobs.models import Jobs
import os,json

class Command(BaseCommand):
    help = 'Create Jobs.'

    def handle(self,*args,**kwargs):
        Jobs.objects.all().delete()
        contact_info = '''
            Abhishek Sahu
            9880907530'''
        jobs_json_data_file = os.path.join(os.getcwd(), 'jobs\management\commands\job_data.json')
        with open(jobs_json_data_file, "r") as read_file:
                job_data = json.load(read_file)
                jobs = job_data['jobs']
                jobs_bulk = [Jobs(title=job['title'], 
                                                    company=job['company'],
                                                    location=job['location'],
                                                    description=job['description'],
                                                    requirements=job['requirements'],
                                                    posted_date=job['posted_date'],
                                                    expiration_date=job['expiration_date'],
                                                    contact_information=contact_info) 
                                                    for job in jobs]
                Jobs.objects.bulk_create(jobs_bulk)
                print('20 Job has been created.')