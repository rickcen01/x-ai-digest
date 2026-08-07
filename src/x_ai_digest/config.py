from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


HOME_FEATURES: dict[str, bool] = {
    "rweb_video_screen_enabled": False,
    "rweb_cashtags_enabled": True,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": True,
    "rweb_tipjar_consumption_enabled": False,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "rweb_cashtags_composer_attachment_enabled": True,
    "responsive_web_jetfuel_frame": True,
    "responsive_web_grok_share_attachment_enabled": True,
    "responsive_web_grok_annotations_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "rweb_conversational_replies_downvote_enabled": False,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "content_disclosure_indicator_enabled": True,
    "content_disclosure_ai_generated_indicator_enabled": True,
    "responsive_web_grok_show_grok_translated_post": True,
    "responsive_web_grok_analysis_button_from_backend": True,
    "post_ctas_fetch_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": False,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_imagine_annotation_enabled": True,
    "responsive_web_grok_community_note_auto_translation_is_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}


@dataclass(frozen=True)
class Settings:
    root: Path
    config_path: Path
    account_db: Path
    proxy: str | None
    source: str
    browser: dict[str, Any]
    home: dict[str, Any]
    digest: dict[str, Any]
    llm: dict[str, Any]
    delivery: dict[str, Any]

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def state_dir(self) -> Path:
        return self.root / "state"


def _resolve_path(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def load_settings(config_path: str | Path) -> Settings:
    path = Path(config_path).expanduser().resolve()
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    root = path.parent
    account_db = _resolve_path(root, raw.get("account_db", "data/accounts.db"))
    proxy = raw.get("proxy") or None
    source = str(raw.get("source") or "browser").strip().lower()
    browser = dict(raw.get("browser") or {})
    home = dict(raw.get("home") or {})
    digest = dict(raw.get("digest") or {})
    llm = dict(raw.get("llm") or {})
    delivery = dict(raw.get("delivery") or {})

    home.setdefault("operation_id", "psvmu2kIj08INJBBiZVgMw/HomeTimeline")
    home.setdefault("count", 20)
    home.setdefault("language", "zh-cn")
    home.setdefault("timeout_seconds", 45)
    home.setdefault("auto_discover_operation", True)
    browser.setdefault("profile_dir", "data/browser-profile")
    browser["profile_dir"] = str(_resolve_path(root, str(browser["profile_dir"])))
    browser.setdefault("executable_path", "")
    browser.setdefault("headless", True)
    browser.setdefault("timeout_seconds", 60)
    browser.setdefault("login_timeout_minutes", 15)
    digest.setdefault("title", "X 每日 AI 情报")
    digest.setdefault("max_items", 10)
    digest.setdefault("lookback_hours", 96)
    digest.setdefault("minimum_keyword_score", 2.0)
    digest.setdefault("keywords", [])
    delivery.setdefault("channels", ["local"])

    return Settings(
        root=root,
        config_path=path,
        account_db=account_db,
        proxy=proxy,
        source=source,
        browser=browser,
        home=home,
        digest=digest,
        llm=llm,
        delivery=delivery,
    )
