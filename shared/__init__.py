# shared/__init__.py
# makes a shared python package

from . import mail
from . import utils
from . import db

__all__ = ["mail", "utils", "db"]