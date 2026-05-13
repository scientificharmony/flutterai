from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    anthropic_api_key: str = ""
    t212_api_key: str = ""
    t212_secret: str | None = None
    t212_env: str = "demo"
    claude_model: str = "claude-3-5-sonnet-20241022"
    claude_max_tokens: int = 550
    claude_max_candidates: int = 3
    enable_claude_prompt_cache: bool = True
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
    min_push_action_strength: int = 75
    scheduled_min_formula_score_for_claude: int = 70
    sell_target_pct: float = 8.0
    stop_loss_pct: float = 5.0
    stale_position_days: int = 14
    forex_provider: str = "mock"
    forex_demo_balance: float = 5000.0
    forex_risk_bps: int = 50
    forex_min_signal_strength: int = 78
    enable_forex_auto_close: bool = False
    enable_forex_entry_alerts: bool = True
    forex_entry_scan_minutes: int = 15
    forex_entry_cooldown_hours: int = 4
    ig_api_key: str = ""
    ig_username: str = ""
    ig_password: str = ""
    ig_account_type: str = "DEMO"

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
    def CLAUDE_MAX_TOKENS(self) -> int: return self.claude_max_tokens
    @property
    def CLAUDE_MAX_CANDIDATES(self) -> int: return self.claude_max_candidates
    @property
    def ENABLE_CLAUDE_PROMPT_CACHE(self) -> bool: return self.enable_claude_prompt_cache
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
    @property
    def MIN_PUSH_ACTION_STRENGTH(self) -> int: return self.min_push_action_strength
    @property
    def SCHEDULED_MIN_FORMULA_SCORE_FOR_CLAUDE(self) -> int: return self.scheduled_min_formula_score_for_claude
    @property
    def FOREX_PROVIDER(self) -> str: return self.forex_provider
    @property
    def FOREX_DEMO_BALANCE(self) -> float: return self.forex_demo_balance
    @property
    def FOREX_RISK_BPS(self) -> int: return self.forex_risk_bps
    @property
    def FOREX_MIN_SIGNAL_STRENGTH(self) -> int: return self.forex_min_signal_strength
    @property
    def ENABLE_FOREX_AUTO_CLOSE(self) -> bool: return self.enable_forex_auto_close
    @property
    def ENABLE_FOREX_ENTRY_ALERTS(self) -> bool: return self.enable_forex_entry_alerts
    @property
    def FOREX_ENTRY_SCAN_MINUTES(self) -> int: return self.forex_entry_scan_minutes
    @property
    def FOREX_ENTRY_COOLDOWN_HOURS(self) -> int: return self.forex_entry_cooldown_hours
    @property
    def IG_API_KEY(self) -> str: return self.ig_api_key
    @property
    def IG_USERNAME(self) -> str: return self.ig_username
    @property
    def IG_PASSWORD(self) -> str: return self.ig_password
    @property
    def IG_ACCOUNT_TYPE(self) -> str: return self.ig_account_type


settings = Settings()
