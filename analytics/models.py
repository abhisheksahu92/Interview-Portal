"""Analytics models.

The hiring domain keeps only the *current* stage of an application, so this app
owns the history table every funnel/velocity metric needs:
:class:`StageTransition` rows are appended by signals on ``jobs.Application``
(see :mod:`analytics.signals`) and can be seeded for existing data with
``manage.py backfill_stage_transitions``.
"""

from django.db import models


class StageTransition(models.Model):
    """One recorded move of an application between stages and/or statuses."""

    application = models.ForeignKey(
        "jobs.Application", on_delete=models.CASCADE, related_name="stage_transitions"
    )
    from_stage = models.ForeignKey(
        "jobs.PipelineStage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transitions_out",
    )
    to_stage = models.ForeignKey(
        "jobs.PipelineStage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transitions_in",
    )
    status_after = models.CharField(max_length=10)
    at = models.DateTimeField()

    class Meta:
        ordering = ["at", "id"]
        indexes = [
            models.Index(fields=["application", "at"]),
            models.Index(fields=["at"]),
        ]

    def __str__(self):
        return f"{self.application_id}: {self.from_stage_id} → {self.to_stage_id} ({self.status_after})"

    @property
    def company(self):
        return self.application.job.company
