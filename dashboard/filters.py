from candidate.models import Candidate
import django_filters

class CandidateFilter(django_filters.FilterSet):
    first_name = django_filters.CharFilter(lookup_expr='icontains')
    last_name = django_filters.CharFilter(lookup_expr='icontains')
    phone = django_filters.NumberFilter(lookup_expr='icontains')
    email = django_filters.CharFilter(lookup_expr='icontains')
    noticeperiod = django_filters.CharFilter(lookup_expr='icontains')
    skill = django_filters.NumberFilter(lookup_expr='icontains')
    status = django_filters.CharFilter(lookup_expr='icontains')
    class Meta:
        model = Candidate
        fields = ['first_name', 'last_name','phone','email','noticeperiod','skill','status']