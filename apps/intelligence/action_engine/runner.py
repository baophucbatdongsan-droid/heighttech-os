from .engine import ActionEngine


def run_action_engine(tenant_id):

    engine = ActionEngine(tenant_id)

    alerts = engine.run()

    return alerts