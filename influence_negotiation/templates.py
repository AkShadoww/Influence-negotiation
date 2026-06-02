"""
Email templates for the creator negotiation funnel.
Each function returns (subject, body) tuple.

brand_name / manager_name / campaign_deadline are passed in per creator so a
single backend can negotiate for many brands/campaigns at once. When a caller
passes None (e.g. a creator seeded without a brand), the config DEFAULT_*
fallbacks are used.
"""

from typing import List, Optional, Tuple
from config import (
    DEFAULT_BRAND_NAME,
    DEFAULT_CAMPAIGN_DEADLINE,
    DEFAULT_MANAGER_NAME,
    REFERENCE_ACCOUNTS,
)


def _ref_accounts_block(accounts: List[Tuple[str, str]]) -> str:
    return "\n".join(f"{handle} ({views})" for handle, views in accounts)


def reply1(
    creator_name: str,
    brand_name: Optional[str] = None,
    campaign_deadline: Optional[str] = None,
    manager_name: Optional[str] = None,
    **kwargs,
) -> Tuple[str, str]:
    """Brand collab details — sent when creator expresses interest."""
    brand_name = brand_name or DEFAULT_BRAND_NAME
    campaign_deadline = campaign_deadline or DEFAULT_CAMPAIGN_DEADLINE
    manager_name = manager_name or DEFAULT_MANAGER_NAME
    refs = _ref_accounts_block(REFERENCE_ACCOUNTS)
    subject = f"Re: {brand_name} x {creator_name} Collaboration"
    body = f"""Hi {creator_name},

So great to hear from you! Here are all the details:

Content Style
We'd love the content to be in your natural style, with {brand_name} integrated effortlessly. Nothing overly promotional. Full creative freedom on your end.

Deliverables & Rates
- Depending on your rate, we'd love to do a 2 or more video package deal.
- We're keen on exploring a long-term retainer deal. These initial videos would act as a test run, and if things go well, this could turn into a guaranteed monthly brand deal!
- Additionally, through INFLUENCE, we aim to bring you consistent deal flow from other brands we work with.

Platforms
We'd like the content to be posted on Instagram primarily, and cross-posted on TikTok & YouTube Shorts.

Timelines
We're flexible, but we'd ideally like all videos posted by {campaign_deadline}.

Past content references
{refs}

If everything sounds good, please let me know your rates :)

- {manager_name}"""
    return subject, body


def followup1(
    creator_name: str,
    brand_name: Optional[str] = None,
    manager_name: Optional[str] = None,
    **kwargs,
) -> Tuple[str, str]:
    """Follow-up after Reply 1 — no rate received in 2 days."""
    brand_name = brand_name or DEFAULT_BRAND_NAME
    manager_name = manager_name or DEFAULT_MANAGER_NAME
    subject = f"Re: {brand_name} x {creator_name} Collaboration"
    body = f"""Hi {creator_name},

Did you get a chance to check my last email?

Please let me know your rate! Would love to collaborate. :)

- {manager_name}"""
    return subject, body


def reply2(
    creator_name: str,
    flat_rate: float,
    flat_bonus_threshold_views: int,
    flat_bonus_amount: float,
    view_based_rate: float,
    view_target: int,
    avg_views: int,
    video_count: int = 2,
    brand_name: Optional[str] = None,
    manager_name: Optional[str] = None,
    **kwargs,
) -> Tuple[str, str]:
    """Price offer — sent after receiving creator's rate."""
    brand_name = brand_name or DEFAULT_BRAND_NAME
    manager_name = manager_name or DEFAULT_MANAGER_NAME
    subject = f"Re: {brand_name} x {creator_name} Collaboration"
    flat_total = flat_rate + flat_bonus_amount
    body = f"""Hi {creator_name},

Thanks for sharing your rates!

We usually do performance-based deals with all our creators. We'd love to propose a slightly different view based offer:

Option 1: Flat Rate + Bonus (${flat_rate:,.0f})
• ${flat_rate:,.0f} flat for {video_count} videos
• ${flat_bonus_amount:,.0f} bonus if the combined views cross {flat_bonus_threshold_views:,} on Instagram

Option 2: View-Based Offer (${flat_total:,.0f})
• ${view_based_rate:,.0f} for a minimum of {view_target:,} combined total views on Instagram.
• Views can come from a single video or multiple posts - combined total views will be counted. So if the first video ends up crossing {view_target * 2:,} views, you don't have to upload further videos!
• Views counted for 7 days from each post's publish date.
• Considering your recent performance, I'd anticipate you can easily cross the {view_target:,} view goal with {video_count} posts.
• As I mentioned earlier, you have full creative freedom. So you can create engaging content around {brand_name} without the content feeling like an ad!
• You can commit to fewer views if you'd like. If you're confident committing to higher views, we're open to that too. And payment can be adjusted accordingly!
• No ad rights or exclusivity required.

Payment details
We do direct bank transfers. Payment will be initiated within 7 working days of completing and posting all the agreed deliverables!

Would love to work together and land on something that works well for both sides! Let me know your thoughts :)

- {manager_name}"""
    return subject, body


def followup2(
    creator_name: str,
    brand_name: Optional[str] = None,
    manager_name: Optional[str] = None,
    **kwargs,
) -> Tuple[str, str]:
    """Follow-up after Reply 2 — no decision received in 2 days."""
    brand_name = brand_name or DEFAULT_BRAND_NAME
    manager_name = manager_name or DEFAULT_MANAGER_NAME
    subject = f"Re: {brand_name} x {creator_name} Collaboration"
    body = f"""Hi {creator_name},

Did you get a chance to check my last email?

Looking fwd to hearing your thoughts! We'd love to collab with you. :)

- {manager_name}"""
    return subject, body


def high_rate_rejection(
    creator_name: str,
    quoted_rate: float,
    brand_name: Optional[str] = None,
    manager_name: Optional[str] = None,
    **kwargs,
) -> Tuple[str, str]:
    """Sent when creator's quoted rate exceeds our budget cap."""
    brand_name = brand_name or DEFAULT_BRAND_NAME
    manager_name = manager_name or DEFAULT_MANAGER_NAME
    subject = f"Re: {brand_name} x {creator_name} Collaboration"
    body = f"""Hi {creator_name},

I really appreciate the proposal, but ${quoted_rate:,.0f} per video is higher than what we typically pay creators in your current view range, so we won't be able to move forward with those terms at this time.

We love your work, so if anything changes on our end or if you're open to revisiting the rates we discussed, please let me know. I'd love to find a way to work together!

- {manager_name}"""
    return subject, body


def delay_email(
    creator_name: str,
    brand_name: Optional[str] = None,
    manager_name: Optional[str] = None,
    **kwargs,
) -> Tuple[str, str]:
    """Sent when creator is not available / timing is off."""
    brand_name = brand_name or DEFAULT_BRAND_NAME
    manager_name = manager_name or DEFAULT_MANAGER_NAME
    subject = f"Re: {brand_name} x {creator_name} Collaboration"
    body = f"""Hi {creator_name},

Thanks for getting back to me.

We are currently making a few strategic changes to our upcoming campaigns, so I will definitely reach out again soon! :)

- {manager_name}"""
    return subject, body


def acceptance_confirmation(
    creator_name: str,
    brand_name: Optional[str] = None,
    manager_name: Optional[str] = None,
    **kwargs,
) -> Tuple[str, str]:
    """Sent when creator accepts the deal — placeholder until contract flow is built."""
    brand_name = brand_name or DEFAULT_BRAND_NAME
    manager_name = manager_name or DEFAULT_MANAGER_NAME
    subject = f"Re: {brand_name} x {creator_name} Collaboration"
    body = f"""Hi {creator_name},

That's wonderful news — we're excited to work with you!

I'll be in touch shortly with the next steps to get everything set up.

- {manager_name}"""
    return subject, body
