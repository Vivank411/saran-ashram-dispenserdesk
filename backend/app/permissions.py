ROLES = ("Admin", "Biller")

PERMISSIONS: dict[str, str] = {
    "bill.create": "Create and confirm bills",
    "bill.view": "View bills",
    "bill.reverse": "Reverse bills",
    "stock.view": "View stock, ledger and alerts",
    "stock.request": "Request stock or rate changes",
    "stock.approve": "Approve stock or rate changes (and change stock directly)",
    "alerts.ack": "Acknowledge low-stock alerts",
    "reports.view": "View reports",
    "sync.view": "View synchronization monitor",
    "sync.manage": "Run synchronization and resolve conflicts",
    "audit.view": "View audit log",
    "users.manage": "Manage users",
    "settings.manage": "Change system settings",
}

ROLE_PERMS: dict[str, tuple[str, ...]] = {
    # Admin can do everything.
    "Admin": ("*",),
    # Biller: billing, plus inventory changes that take effect only after an Admin approves them.
    "Biller": ("bill.create", "bill.view", "stock.view", "stock.request", "alerts.ack", "reports.view"),
}


def has_perm(role: str, perm: str) -> bool:
    perms = ROLE_PERMS.get(role, ())
    return "*" in perms or perm in perms


def perms_for(role: str) -> list[str]:
    return [p for p in PERMISSIONS if has_perm(role, p)]
