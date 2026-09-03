from django.db import models
from django.contrib.auth.models import User

class Employee(models.Model):
    skill_choices  = (('Python','Python'),('Java','Java'))
    level_choices  = (('L1','L1'),('L2','L2'),('HR','HR'))
    approval_choices  = (('Approved','Approved'),('Rejected','Rejected'),('Pending','Pending'))

    employee_username   = models.OneToOneField(User,related_name='+',on_delete=models.CASCADE)
    employee_name       = models.CharField(verbose_name = 'Employee Name', max_length=50)
    employee_email      = models.EmailField(verbose_name = 'Official Email',unique = True,null = False,blank = False)
    employee_skill      = models.CharField(verbose_name = 'Skill',max_length=50,choices = skill_choices,null = False,blank = False)
    employee_level      = models.CharField(verbose_name= 'Level',max_length=50,choices = level_choices,null = False,blank = False)
    employee_status     = models.CharField(verbose_name='Approval Status', default='Pending',choices=approval_choices , max_length= 50)

    class Meta:
        verbose_name = "Employee"
        verbose_name_plural = "Employees"

    def __str__(self):
        return self.employee_name


