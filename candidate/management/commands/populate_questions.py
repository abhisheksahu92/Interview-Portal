from django.core.management.base import BaseCommand
from django.conf import settings
from candidate.models import CandidateQuestionModel
import os,json

class Command(BaseCommand):
    help = 'Seed the Candidates Questions database'

    def handle(self,*args,**kwargs):    
        try:
            CandidateQuestionModel.objects.all().delete()
            python_json_data_file = os.path.join(os.getcwd(), 'candidate\management\commands\questionnaire_python.json')
            python_json_data_file_1 = os.path.join(os.getcwd(), 'candidate\management\commands\questionnaire_python_2.json')
            java_json_data_file = os.path.join(os.getcwd(), 'candidate\management\commands\questionnaire_java.json')
            with open(python_json_data_file, "r") as read_file:
                question_data = json.load(read_file)
                questions = question_data['questions']
                questions_bulk = [CandidateQuestionModel(question=question['question'], 
                                                    option1=question['option1'],
                                                    option2=question['option2'],
                                                    option3=question['option3'],
                                                    option4=question['option4'],
                                                    answer=question['answer']) 
                                                    for question in questions]
                CandidateQuestionModel.objects.bulk_create(questions_bulk)
                print('100 Questions has been created.')

            with open(python_json_data_file_1, "r") as read_file:
                question_data = json.load(read_file)
                questions = question_data['questions']
                questions_bulk = [CandidateQuestionModel(question=question['question'], 
                                                    option1=question['options'][0],
                                                    option2=question['options'][1],
                                                    option3=question['options'][2],
                                                    option4=question['options'][3],
                                                    answer=question['answer']) 
                                                    for question in questions]
                CandidateQuestionModel.objects.bulk_create(questions_bulk)
                print('100 Python Questions has been created.')

            with open(java_json_data_file, "r") as read_file:
                question_data = json.load(read_file)
                questions = question_data['questions']
                questions_bulk = [CandidateQuestionModel(question=question['question'], 
                                                    option1=question['options'][0],
                                                    option2=question['options'][1],
                                                    option3=question['options'][2],
                                                    option4=question['options'][3],
                                                    answer=question['answer'],
                                                    skill='Java')
                                                    for question in questions]
                CandidateQuestionModel.objects.bulk_create(questions_bulk)
                print('100 Java Questions has been created.')
        except Exception as e:
            print(e)