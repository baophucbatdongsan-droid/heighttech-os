from rest_framework.exceptions import PermissionDenied
from apps.tenants.models_subscription import SubscriptionTier


def require_tier(required_tier):
    tier_rank = {
        SubscriptionTier.FREE: 0,
        SubscriptionTier.PRO: 1,
        SubscriptionTier.ENTERPRISE: 2,
    }

    def decorator(view_func):
        def wrapper(view, request, *args, **kwargs):
            tenant = getattr(request.user, "tenant", None)
            if not tenant or not hasattr(tenant, "subscription"):
                raise PermissionDenied("No subscription")

            current = tenant.subscription.tier

            if tier_rank[current] < tier_rank[required_tier]:
                raise PermissionDenied("Upgrade required")

            return view_func(view, request, *args, **kwargs)
        return wrapper
    return decorator