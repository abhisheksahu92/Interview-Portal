"""Seed the three sample question packs (Python, Django, Java).

Idempotent: re-running updates the existing packs in place.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from marketplace.models import QuestionPack

_PYTHON = [
    ("Which built-in returns an immutable sequence?", ["list", "tuple", "set", "dict"], 1, "EASY"),
    ("What does `len({'a': 1, 'b': 2})` return?", ["1", "2", "3", "TypeError"], 1, "EASY"),
    ("Which keyword defines a generator?", ["return", "yield", "async", "lambda"], 1, "EASY"),
    ("What is the result of `bool([])`?", ["True", "False", "None", "Error"], 1, "EASY"),
    ("Which method adds one item to a list?", ["append", "extend", "insert_all", "push"], 0, "EASY"),
    ("Which module provides dataclasses?", ["typing", "dataclasses", "attrs", "struct"], 1, "MEDIUM"),
    ("What does the walrus operator `:=` do?", ["Compares", "Assigns in an expression", "Unpacks", "Slices"], 1, "MEDIUM"),
    ("Which manager guarantees a file is closed?", ["try", "with", "finally-only", "del"], 1, "MEDIUM"),
    ("What is a GIL?", ["Garbage collector", "Global interpreter lock", "Generic import loader", "A linter"], 1, "MEDIUM"),
    ("Which is NOT thread-safe by itself?", ["list.append", "dict.setdefault", "read-modify-write of an int", "queue.Queue.put"], 2, "HARD"),
]
_DJANGO = [
    ("Which file maps URLs to views?", ["models.py", "urls.py", "apps.py", "admin.py"], 1, "EASY"),
    ("Which command creates migration files?", ["migrate", "makemigrations", "sqlmigrate", "check"], 1, "EASY"),
    ("What does an ORM `QuerySet` do when sliced?", ["Executes immediately", "Adds LIMIT/OFFSET", "Raises", "Copies rows"], 1, "MEDIUM"),
    ("Which setting lists middleware?", ["MIDDLEWARE_CLASSES", "MIDDLEWARE", "INSTALLED_MIDDLEWARE", "HOOKS"], 1, "EASY"),
    ("Which field type stores JSON natively?", ["TextField", "JSONField", "BlobField", "DictField"], 1, "EASY"),
    ("What does `select_related` optimise?", ["Many-to-many", "Forward FK joins", "Reverse FK prefetch", "Aggregates"], 1, "MEDIUM"),
    ("Where do signal receivers usually get registered?", ["settings.py", "AppConfig.ready", "urls.py", "wsgi.py"], 1, "MEDIUM"),
    ("Which decorator restricts a view to POST?", ["require_GET", "require_POST", "csrf_exempt", "login_required"], 1, "EASY"),
    ("What guards against duplicate form submissions best?", ["CSRF token", "Idempotent handlers", "GET requests", "Debug mode"], 1, "HARD"),
    ("Describe how you would scope every query to a tenant.", [], None, "HARD"),
]
_JAVA = [
    ("Which keyword prevents subclassing?", ["static", "final", "sealed", "private"], 1, "EASY"),
    ("What is the parent of every class?", ["Class", "Object", "Base", "Any"], 1, "EASY"),
    ("Which collection keeps insertion order?", ["HashSet", "LinkedHashSet", "TreeSet", "PriorityQueue"], 1, "MEDIUM"),
    ("Which type is immutable?", ["StringBuilder", "String", "ArrayList", "HashMap"], 1, "EASY"),
    ("What does JVM stand for?", ["Java Virtual Machine", "Java Version Manager", "Just Virtual Memory", "Java Vendor Model"], 0, "EASY"),
    ("Which interface enables lambda use?", ["Serializable", "Functional interface", "Cloneable", "Comparable only"], 1, "MEDIUM"),
    ("Which exception is checked?", ["NullPointerException", "IOException", "ArithmeticException", "ClassCastException"], 1, "MEDIUM"),
    ("What does `volatile` guarantee?", ["Atomicity", "Visibility", "Ordering of all ops", "Locking"], 1, "HARD"),
    ("Which GC region holds short-lived objects?", ["Old gen", "Young gen", "Metaspace", "Code cache"], 1, "MEDIUM"),
    ("Explain the difference between `equals` and `==`.", [], None, "MEDIUM"),
]

PACKS = [
    {
        "title": "Python Fundamentals",
        "slug": "python-fundamentals",
        "skill_name": "Python",
        "description": "Ten screening questions covering Python syntax, data types and concurrency basics.",
        "price_inr": Decimal("0"),
        "author": "Interview Portal",
        "rows": _PYTHON,
    },
    {
        "title": "Django Essentials",
        "slug": "django-essentials",
        "skill_name": "Django",
        "description": "Ten questions on Django URLs, migrations, the ORM and request handling.",
        "price_inr": Decimal("499"),
        "author": "Interview Portal",
        "rows": _DJANGO,
    },
    {
        "title": "Core Java",
        "slug": "core-java",
        "skill_name": "Java",
        "description": "Ten questions on Java language features, collections and the JVM.",
        "price_inr": Decimal("499"),
        "author": "Interview Portal",
        "rows": _JAVA,
    },
]


def build_questions(rows):
    questions = []
    for text, options, correct, difficulty in rows:
        kind = "MCQ" if options else "TEXT"
        questions.append(
            {
                "kind": kind,
                "text": text,
                "options": list(options),
                "correct_option": correct,
                "difficulty": difficulty,
            }
        )
    return questions


def seed_packs():
    """Create/update the sample packs; returns the list of packs."""
    packs = []
    for spec in PACKS:
        pack, _ = QuestionPack.objects.update_or_create(
            slug=spec["slug"],
            defaults={
                "title": spec["title"],
                "skill_name": spec["skill_name"],
                "description": spec["description"],
                "price_inr": spec["price_inr"],
                "author": spec["author"],
                "questions": build_questions(spec["rows"]),
                "published": True,
            },
        )
        packs.append(pack)
    return packs


class Command(BaseCommand):
    help = "Seed the sample marketplace question packs (idempotent)."

    def handle(self, *args, **options):
        packs = seed_packs()
        for pack in packs:
            self.stdout.write(f"{pack.slug}: {pack.question_count} questions, ₹{pack.price_inr}")
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(packs)} packs."))
