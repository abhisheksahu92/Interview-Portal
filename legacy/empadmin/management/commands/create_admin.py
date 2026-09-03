from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils.crypto import get_random_string

class Command(BaseCommand):
    help = 'Create Admin user.'

    def add_arguments(self, parser):
        parser.add_argument('-username', type=str, help='Username')
        parser.add_argument('-password', type=str, help='Password')
        parser.add_argument('-email', type=str, help='Email')
        parser.add_argument('-first_name', type=str, help='First Name')
        parser.add_argument('-last_name', type=str, help='Last Name')

    def handle(self, *args, **kwargs):
        username = kwargs['username']
        password = kwargs['password']
        email = kwargs['email']
        first_name = kwargs['first_name']
        last_name = kwargs['last_name']
        data = {'username':get_random_string(10) if username is None else username, 
                                 'email':'' if email is None else email, 
                                 'password':'123' if password is None else password,
                                 'first_name':'' if first_name is None else first_name,
                                 'last_name':'' if last_name is None else last_name,
                                 'is_superuser':True}
        print(data)
        User.objects.create_user(**data)