"""Question-pack storefront models."""

from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class QuestionPack(models.Model):
    """A sellable bundle of questions, authored by us or a partner."""

    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True)
    skill_name = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    price_inr = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    questions = models.JSONField(default=list, blank=True)
    published = models.BooleanField(default=False)
    author = models.CharField(max_length=120, blank=True)
    downloads = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["price_inr", "title"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self.unique_slug(self.title)
        super().save(*args, **kwargs)

    @classmethod
    def unique_slug(cls, title):
        base = slugify(title) or "pack"
        slug, i = base, 2
        while cls.objects.filter(slug=slug).exists():
            slug = f"{base}-{i}"
            i += 1
        return slug

    @property
    def is_free(self):
        return (self.price_inr or 0) <= 0

    @property
    def question_count(self):
        return len(self.questions or [])

    def preview(self, n=3):
        """The first ``n`` questions, with the answer key stripped."""
        preview = []
        for item in (self.questions or [])[:n]:
            row = dict(item)
            row.pop("correct_option", None)
            preview.append(row)
        return preview

    def is_installed_for(self, company):
        if company is None:
            return False
        return PackPurchase.objects.filter(company=company, pack=self).exists()


class PackPurchase(models.Model):
    """A company's entitlement to a pack (free installs included)."""

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="pack_purchases"
    )
    pack = models.ForeignKey(QuestionPack, on_delete=models.CASCADE, related_name="purchases")
    invoice_ref = models.CharField(max_length=80, blank=True)
    purchased_at = models.DateTimeField(default=timezone.now)
    purchased_by = models.ForeignKey(
        "core.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    questions_created = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-purchased_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "pack"], name="marketplace_unique_company_pack"
            )
        ]

    def __str__(self):
        return f"{self.company} owns {self.pack}"
