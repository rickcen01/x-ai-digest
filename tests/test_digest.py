from datetime import datetime, timedelta, timezone

from x_ai_digest.digest import render_structured_digest, score_posts
from x_ai_digest.models import DigestPost


def make_post(post_id: str, text: str, likes: int = 0) -> DigestPost:
    return DigestPost(
        id=post_id,
        url=f"https://x.com/example/status/{post_id}",
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        username="example",
        display_name="Example",
        text=text,
        language="en",
        likes=likes,
    )


def test_score_posts_filters_and_ranks_ai_content():
    posts = [
        make_post("1", "New open source LLM reasoning model released", likes=100),
        make_post("2", "A normal travel photo", likes=10000),
        make_post("3", "OpenAI released a new AI agent", likes=500),
    ]
    ranked = score_posts(posts, ["openai", "ai agent", "llm", "reasoning model"], 24, 2.0)
    assert [post.id for post in ranked] == ["3", "1"]
    assert "openai" in ranked[0].matched_keywords


def test_render_keeps_source_links():
    post = make_post("1", "OpenAI released a new AI agent", likes=100)
    post.links = ["https://example.com/release"]
    report = render_structured_digest([post], "Daily", 20)
    assert "https://x.com/example/status/1" in report
    assert "https://example.com/release" in report
    assert "本次读取 20 条" in report

