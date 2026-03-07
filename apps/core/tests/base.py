from django.test import TestCase
from apps.core.audit import audit_disabled



class NoAuditTestCase(TestCase):
    def setUp(self):
        self._audit_ctx = audit_disabled()
        self._audit_ctx.__enter__()

    def tearDown(self):
        self._audit_ctx.__exit__(None, None, None)