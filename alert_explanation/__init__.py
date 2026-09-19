"""Evidence-bound explanations for manufacturing alerts."""
from .models import AlertInput, Explanation
from .service import explain_alert

__all__ = ["AlertInput", "Explanation", "explain_alert"]

