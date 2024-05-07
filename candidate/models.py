from django.db import models
from django.utils.encoding import smart_text
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from employee.models import Employee
from django.core.files.storage import FileSystemStorage

# Create your models here.
class Candidate(models.Model):
    source_choices = (('Referral', 'Referral'), ('Job Portal', 'Job Portal'), ('Walk In', 'Walk In'))
    skill_choices = (('Python', 'Python'), ('Java', 'Java'))
    result_choice = (('Selected', 'Selected'), ('Rejected', 'Rejected'), ('Pending', 'Pending'))

    username = models.OneToOneField(User,related_name='+',on_delete=models.CASCADE)
    first_name = models.CharField(verbose_name='First Name',null=False,blank=False,max_length=50)
    last_name = models.CharField(verbose_name='Last Name',null=False,blank=False,max_length=50)
    email = models.EmailField(verbose_name='Email',unique=True,null=False,blank=False)
    phone = models.PositiveBigIntegerField(verbose_name='Phone Number',unique=True,null=False,blank=False)
    dateofbirth = models.DateField(verbose_name='Date of Birth',null=False,blank=False)
    experience = models.DecimalField(verbose_name='Experience',null=False,blank=False,max_digits=5, decimal_places=2,help_text='Please enter in years')
    noticeperiod = models.IntegerField(verbose_name='Notice Period', blank=False, null=False,help_text='Please enter in months')
    source = models.CharField(verbose_name='Source', max_length=10, choices=source_choices, default='Walk In')
    skill = models.CharField(max_length=10, default='Python', choices=skill_choices, null=False, blank=False)
    resume = models.FileField(verbose_name='Resume', upload_to='documents/')
    created_at = models.DateTimeField(verbose_name='Created At', auto_now=False, auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name='Updated At', auto_now=True, auto_now_add=False)
    status = models.CharField(verbose_name='Status', default='Pending',choices=result_choice , max_length= 50)
    assessment_data = models.JSONField(verbose_name='Score', null=True)
    assessment_result = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at','-updated_at']
        verbose_name = "Candidate"
        verbose_name_plural = "Candidates"

    def __str__(self):
        return smart_text(self.username)

    def __unicode__(self):
        return smart_text(self.username)

class CandidateResult(models.Model):
    result_choice   = (('Selected','Selected'),('Rejected','Rejected'),('Pending','Pending'))
    candidate_id    = models.ForeignKey(Candidate,related_name='+',on_delete=models.CASCADE)
    status_l1       = models.CharField(verbose_name='L1 Status', default='Pending',choices=result_choice , max_length= 50)
    feedback_l1     = models.TextField(verbose_name='L1 Feedback', null=True, blank=True)
    l1_by           = models.ForeignKey(Employee,related_name='+',on_delete=models.CASCADE, null=True, blank=True)
    l1_at           = models.DateTimeField(verbose_name='L1 Date',null=True)
    status_l2       = models.CharField(verbose_name='L2 Status', default='Pending',choices=result_choice , max_length= 50)
    feedback_l2     = models.TextField(verbose_name='L2 Feedback', null=True, blank=True)
    l2_by           = models.ForeignKey(Employee, related_name='+', on_delete=models.CASCADE, null=True, blank=True)
    l2_at           = models.DateTimeField(verbose_name='L2 Date',null=True)
    status_hr       = models.CharField(verbose_name='HR Status', default='Pending',choices=result_choice , max_length= 50)
    feedback_hr     = models.TextField(verbose_name='HR Feedback', null=True, blank=True)
    hr_by           = models.ForeignKey(Employee, related_name='+', on_delete=models.CASCADE, null=True, blank=True)
    hr_at           = models.DateTimeField(verbose_name='HR Date',null=True)

# method for updating
@receiver(post_save, sender=Candidate)
def update_stock(sender, instance, **kwargs):
    CandidateResult.objects.get_or_create(candidate_id=instance)

# Create your models here.
class CandidateQuestionModel(models.Model):
    skill_choices = (('Python', 'Python'), ('Java', 'Java'))
    question = models.CharField(max_length=200,null=True)
    skill = models.CharField(max_length=10, default='Python', choices=skill_choices, null=False, blank=False)
    option1 = models.CharField(max_length=200,null=True)
    option2 = models.CharField(max_length=200,null=True)
    option3 = models.CharField(max_length=200,null=True)
    option4 = models.CharField(max_length=200,null=True)
    answer  = models.CharField(max_length=200,null=True)
    
    def __str__(self):
        return self.question
