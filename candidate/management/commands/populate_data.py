from django.core.management.base import BaseCommand
from random import randint
from django.core.files import File
from candidate.models import Candidate,CandidateResult
from employee.models import Employee
from django.contrib.auth.models import User,Group
from faker import Faker
import random,os,json,glob


class Command(BaseCommand):
    help = 'Seed the Candidates and User database'

    def delete_files(self):
        print('Deleting Users,Candidates and Employees')
        User.objects.all().delete()
        CandidateResult.objects.all().delete()
        Candidate.objects.all().delete()
        Employee.objects.all().delete()

        files = glob.glob('media/documents/media/documents/*')
        for f in files:
            os.remove(f)

    def handle(self,*args,**kwargs):    
        try:
            self.delete_files()
            source_choices = ['Referral','Job Portal','Walk In']
            skill_choices = ['Python', 'Java']
            with open('media\documents\Abhishek_Sahu_Python_4.pdf','rb') as file_ref:
                for index in range(50):
                    fake = Faker('en_IN')
                    username = User.objects.create_user(
                        username = f'candidate{index}',
                        password= f'candidate{index}'
                    )
                    group = Group.objects.get(name='Candidate')
                    group.user_set.add(User.objects.get(username=f'candidate{index}'))

                    Candidate.objects.create(username=username,
                                    first_name=fake.first_name(),
                                    last_name=fake.last_name(),
                                    email=fake.email(),
                                    phone=fake.phone_number(),
                                    dateofbirth=fake.date_of_birth(),
                                    experience=randint(1,10),
                                    noticeperiod=random.choice([1,2,3]),
                                    source=random.choice(source_choices),
                                    skill=random.choice(skill_choices),
                                    resume = File(file_ref))
            print('50 Candidates has been created')
        except Exception as e:
            print(e)