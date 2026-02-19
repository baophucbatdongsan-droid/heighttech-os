from django.db import models

class TenantQuerySet(models.QuerySet):
    def for_tenant(self, tenant):
        path = self.model.tenant_path()
        return self.filter(**{path: tenant})

class TenantManager(models.Manager):
    def get_queryset(self):
        return TenantQuerySet(self.model, using=self._db)

    def for_tenant(self, tenant):
        return self.get_queryset().for_tenant(tenant)