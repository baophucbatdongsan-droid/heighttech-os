from __future__ import annotations
from dataclasses import asdict
from typing import Any, Dict, Optional

from apps.rules.models import RuleDecisionLog
from apps.rules.types import EngineContext

class BaseRuleEngine:
    """
    Founder-controlled core. Subclass theo version.
    """

    ENGINE_NAME = "base"

    def __init__(self, ctx: EngineContext):
        self.ctx = ctx

    def log_decision(self, rule_key: str, input_snapshot: Dict[str, Any], output_result: Dict[str, Any]) -> None:
        RuleDecisionLog.objects.create(
            tenant_id=self.ctx.tenant_id,
            shop_id=self.ctx.shop_id,
            industry_code=self.ctx.industry_code,
            rule_version=self.ctx.rule_version,
            rule_key=rule_key,
            request_id=self.ctx.request_id or "",
            input_snapshot=input_snapshot or {},
            output_result=output_result or {},
        )