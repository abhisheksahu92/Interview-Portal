"""ImportBatch.total counts items (zip members + CSV rows), and reports them."""

import pytest
from django.urls import reverse

from talent import services
from talent.models import ImportBatch
from talent.tests.conftest import RESUME_TEXT

pytestmark = pytest.mark.django_db


def _second_resume():
    return (
        RESUME_TEXT.replace("asha.rao@example.test", "ben@example.test")
        .replace("Asha Rao", "Ben Iyer")
        .replace("+91 98765 43210", "+91 98765 40000")
    )


def test_csv_total_counts_rows_not_uploads(company, owner, csv_upload):
    batch = services.run_import(company, [csv_upload()], uploaded_by=owner)
    assert batch.total == 2
    assert [row["outcome"] for row in batch.items] == ["created", "created"]
    assert {row["item"] for row in batch.items} == {
        "asha.rao@example.test",
        "ben@example.test",
    }


def test_zip_with_resumes_and_a_csv_counts_every_item(company, owner, zip_upload):
    csv_text = "\n".join(
        [
            "name,email,phone",
            "Chitra Nair,chitra@example.test,+919000000001",
            "Dev Menon,dev@example.test,+919000000002",
        ]
    )
    upload = zip_upload(
        {"asha.txt": RESUME_TEXT, "nested/ben.txt": _second_resume(), "extra.csv": csv_text}
    )

    batch = services.run_import(company, [upload], uploaded_by=owner)

    # 2 resume files + 2 CSV rows — not "1 upload" and not "3 members".
    assert batch.total == 4
    assert batch.created == 4
    assert batch.processed == 4
    assert batch.percent == 100
    assert len(batch.items) == 4


def test_multiple_resume_uploads_are_counted_individually(company, owner, txt_resume):
    batch = services.run_import(
        company,
        [txt_resume(), txt_resume(name="ben.txt", text=_second_resume())],
        uploaded_by=owner,
    )
    assert batch.total == 2
    assert len(batch.items) == 2


def test_item_rows_record_skips_and_errors(company, owner, csv_upload):
    rows = [
        "name,email,phone",
        "Asha Rao,asha.rao@example.test,+919876543210",
        "No Contact,,",
    ]
    batch = services.run_import(company, [csv_upload(rows)], uploaded_by=owner)
    assert batch.total == 2
    outcomes = {row["outcome"] for row in batch.items}
    assert outcomes == {"created", "error"}
    error_row = next(row for row in batch.items if row["outcome"] == "error")
    assert "row 3" in error_row["item"]
    assert "email" in error_row["message"]


def test_batch_report_lists_every_item(client, company, owner, csv_upload):
    batch = services.run_import(company, [csv_upload()], uploaded_by=owner)
    client.force_login(owner)
    body = client.get(reverse("talent:batch_report", args=[batch.pk])).content.decode()
    assert "Imported items" in body
    assert "asha.rao@example.test" in body
    assert "ben@example.test" in body
    assert "Created" in body


def test_import_batch_starts_empty_and_grows(company, owner, txt_resume):
    batch = services.run_import(company, [txt_resume()], uploaded_by=owner)
    assert batch.status == ImportBatch.DONE
    assert batch.total == 1
