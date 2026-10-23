"""Reviewed route templates, not prefix-based permissions. New routes default to deny."""
PUBLIC_ROUTES = {
    ("GET", "/api/config"), ("GET", "/api/health"),
    ("GET", "/api/dataset/status"), ("GET", "/api/overview"), ("GET", "/api/charts"),
    ("GET", "/api/models/status"), ("GET", "/api/models/evaluation"), ("GET", "/api/models/metadata"),
    ("POST", "/api/forecasts/preview"),
    ("GET", "/api/decisions/metadata"), ("GET", "/api/decisions/demo"),
    ("POST", "/api/decisions/preview"), ("GET", "/api/decisions/plans"),
    ("GET", "/api/decisions/plans/{plan_id}"),
    ("GET", "/api/impact/metadata"), ("GET", "/api/impact/demo"),
    ("POST", "/api/impact/preview"), ("POST", "/api/impact/comparison"),
    ("GET", "/api/impact/records"), ("GET", "/api/impact/summary"),
    ("GET", "/api/impact/records/{service_id}"),
    ("GET", "/api/impact/records/{service_id}/history"),
    ("GET", "/api/impact/records/{service_id}/quality"),
    ("GET", "/api/impact/records/{service_id}/plan"),
}
LOCAL_ONLY_ROUTES = {
    ("POST", "/api/dataset/import"), ("POST", "/api/models/train"),
    ("POST", "/api/forecasts"), ("GET", "/api/forecasts/runs"),
    ("POST", "/api/decisions/plans"), ("GET", "/api/decisions/plans/{plan_id}/export"),
    ("POST", "/api/impact/demo"), ("POST", "/api/impact/records"),
    ("POST", "/api/impact/records/{service_id}/revisions"),
    ("POST", "/api/impact/records/{service_id}/finalize"),
    ("GET", "/api/impact/records/{service_id}/export"),
}
