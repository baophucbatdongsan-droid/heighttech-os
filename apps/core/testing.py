from django.test import Client

def api_client(user=None, tenant_id: int | None = None, host: str = "localhost") -> Client:
    c = Client(HTTP_HOST=host)
    if user:
        c.force_login(user)
    if tenant_id is not None:
        c.defaults["HTTP_X_TENANT_ID"] = str(tenant_id)
    c.defaults["HTTP_ACCEPT"] = "application/json"
    return c