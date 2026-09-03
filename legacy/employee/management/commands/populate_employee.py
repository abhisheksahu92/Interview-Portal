from django.core.management.base import BaseCommand
from employee.models import Employee
from django.contrib.auth.models import User
from faker import Faker
import random,os,json,glob


class Command(BaseCommand):
    help = 'Seed the Employee database'
    def handle(self,*args,**kwargs):    
        try:
            emp_data = Employee.objects.all()
            user_data = User.objects.filter(username__in=[emp.employee_username.username for emp in emp_data])
            user_data.delete()
            emp_data.delete()
            
            file_path = os.path.join(os.getcwd(), 'employee\management\commands\data_file.json')
            with open(file_path, "r") as read_file:
                data = json.load(read_file)
                for emp_data in data['data']:
                    username = User.objects.create_user(
                        username=emp_data['username'],
                        password=emp_data['username'],
                        is_staff = True,
                        email=emp_data['email']
                    )

                    Employee.objects.create(employee_username=username,
                                            employee_name=emp_data['name'],
                                            employee_email=emp_data['email'],
                                            employee_skill=emp_data['skill'],
                                            employee_level=emp_data['level'],
                                            employee_status='Approved')
            print('30 Employees has been created.')
        except Exception as e:
            print(e)