from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    anthropic_api_key: str = ""
    t212_api_key: str = ""
    t212_secret: str | None = None
    t212_env: str = "demo"
    claude_model: str = "claude-3-5-sonnet-20241022"
    app_mode: str = "private_test"
    test_user_id: str = "chris"
    enable_public_auth: bool = False
    enable_billing: bool = False
    enable_order_api: bool = False
    enable_auto_trading: bool = False
    enable_push_notifications: bool = False
    enable_admin_routes: bool = False
    admin_api_token: str = ""
    daily_ai_budget_gbp: float = 2.0
    max_claude_calls_per_day: int = 20
    max_alerts_per_day: int = 5
    database_url: str = "sqlite:///./hey_jimmy.db"
    firebase_service_account_path: str = ""
    free_scans_per_day: int = 3
    pro_scans_per_day: int = 20
    max_risk_pct: float = 10.0
    quiet_hours_start: int = 22
    quiet_hours_end: int = 8

    @property
    def is_private_test(self) -> bool:
        return self.app_mode == "private_test"

    @property
    def t212_base_url(self) -> str:
        return "https://live.trading212.com/api/v0" if self.t212_env.lower() == "live" else "https://demo.trading212.com/api/v0"

    # Uppercase aliases for backward compatibility
    @property
    def ANTHROPIC_API_KEY(self) -> str: return self.anthropic_api_key
    @property
    def T212_API_KEY(self) -> str: return self.t212_api_key
    @property
    def T212_SECRET(self) -> str | None: return self.t212_secret
    @property
    def T212_ENV(self) -> str: return self.t212_env
    @property
    def CLAUDE_MODEL(self) -> str: return self.claude_model
    @property
    def APP_MODE(self) -> str: return self.app_mode
    @property
    def TEST_USER_ID(self) -> str: return self.test_user_id
    @property
    def ENABLE_PUBLIC_AUTH(self) -> bool: return self.enable_public_auth
    @property
    def ENABLE_BILLING(self) -> bool: return self.enable_billing
    @property
    def ENABLE_ORDER_API(self) -> bool: return self.enable_order_api
    @property
    def ENABLE_AUTO_TRADING(self) -> bool: return self.enable_auto_trading
    @property
    def ENABLE_PUSH_NOTIFICATIONS(self) -> bool: return self.enable_push_notifications
    @property
    def ENABLE_ADMIN_ROUTES(self) -> bool: return self.enable_admin_routes
    @property
    def ADMIN_API_TOKEN(self) -> str: return self.admin_api_token
    @property
    def DAILY_AI_BUDGET_GBP(self) -> float: return self.daily_ai_budget_gbp
    @property
    def MAX_CLAUDE_CALLS_PER_DAY(self) -> int: return self.max_claude_calls_per_day
    @property
    def MAX_CLAUDE_SCANS_PER_DAY(self) -> int: return self.max_claude_calls_per_day
    @property
    def MAX_ALERTS_PER_DAY(self) -> int: return self.max_alerts_per_day
    @property
    def DATABASE_URL(self) -> str: return self.database_url
    @property
    def FIREBASE_SERVICE_ACCOUNT_PATH(self) -> str: return self.firebase_service_account_path
    @property
    def FREE_SCANS_PER_DAY(self) -> int: return self.free_scans_per_day
    @property
    def PRO_SCANS_PER_DAY(self) -> int: return self.pro_scans_per_day
    @property
    def MAX_RISK_PCT(self) -> float: return self.max_risk_pct


settings = Settings()
