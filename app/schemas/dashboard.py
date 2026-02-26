from pydantic import BaseModel


class DashboardSummary(BaseModel):
    health_rules_active: int
    warlord_rules_active: int
    sheets_connected: int
    has_whatsapp: bool
    recent_interactions: int
