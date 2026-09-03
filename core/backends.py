"""Authentication backends."""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

UserModel = get_user_model()


class CaseInsensitiveEmailBackend(ModelBackend):
    """Log users in by email, ignoring case.

    Emails are normalised to lower case on write (``User.save``), but rows that
    predate that — or a mixed-case value typed at the login form — must still
    resolve to the same account.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None
        try:
            user = UserModel._default_manager.get(email__iexact=username.strip())
        except UserModel.DoesNotExist:
            # Run the default hasher once to keep timing consistent.
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            user = (
                UserModel._default_manager.filter(email__iexact=username.strip())
                .order_by("pk")
                .first()
            )
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
