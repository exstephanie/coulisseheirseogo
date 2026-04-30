"""
Email Notifier — Formats and sends approval notification emails.

Replaces WhatsApp approval flow. For now, formats email content and logs it.
Actual sending via Resend/SendGrid will be added when serverless function is built.
"""

import logging
from datetime import datetime

logger = logging.getLogger("coulissehair.email_notifier")


def format_approval_email(
    title: str,
    excerpt: str,
    edit_url: str,
    preview_url: str = "",
    word_count: int = 0,
    target_keyword: str = "",
    article_html: str = "",
) -> dict:
    """Format an approval notification email with full article preview.

    Returns dict with subject, html_body, text_body ready for sending.
    """
    # One-click publish URL (triggers GitHub Actions via Vercel API)
    publish_url = "https://upload-eta-ruby.vercel.app/api/publish"
    subject = f"[Coulisse Heir SEO] New post ready: {title}"

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, sans-serif; max-width: 700px; margin: 0 auto; padding: 20px;">
  <div style="background: #1a1a2e; color: white; padding: 20px 24px; border-radius: 8px 8px 0 0;">
    <h2 style="margin: 0; font-size: 1.2rem;">New Blog Post Ready for Approval</h2>
  </div>

  <div style="background: white; border: 1px solid #e0e0e0; border-top: none; padding: 24px;">
    <table style="margin: 0 0 20px 0; font-size: 14px; width: 100%;">
      <tr><td style="padding: 4px 12px 4px 0; color: #666; width: 120px;">Title:</td><td><strong>{title}</strong></td></tr>
      <tr><td style="padding: 4px 12px 4px 0; color: #666;">Keyword:</td><td>{target_keyword}</td></tr>
      <tr><td style="padding: 4px 12px 4px 0; color: #666;">Word count:</td><td>{word_count}</td></tr>
      <tr><td style="padding: 4px 12px 4px 0; color: #666;">Generated:</td><td>{datetime.now().strftime('%d %b %Y, %I:%M %p')}</td></tr>
    </table>

    <div style="margin: 24px 0; text-align: center;">
      <a href="{publish_url}" style="display: inline-block; background: #28a745; color: white; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-size: 16px; font-weight: 600;">Approve & Publish</a>
    </div>

    <p style="color: #666; font-size: 12px; text-align: center;">
      One click to publish. If no action, article stays unpublished.
    </p>
  </div>

  <div style="background: #fafafa; border: 1px solid #e0e0e0; border-top: none; padding: 32px; border-radius: 0 0 8px 8px;">
    <h3 style="color: #666; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; margin: 0 0 16px 0; border-bottom: 1px solid #ddd; padding-bottom: 8px;">Article Preview</h3>
    <div style="font-size: 15px; line-height: 1.7; color: #333;">
      <h1 style="font-size: 1.4rem; color: #1a1a2e;">{title}</h1>
      {article_html}
    </div>
  </div>

  <p style="color: #999; font-size: 11px; text-align: center; margin-top: 16px;">Coulisse Heir SEO Agent v3</p>
</body>
</html>"""

    text_body = f"""New Blog Post Ready for Approval
================================

Title: {title}
Keyword: {target_keyword}
Word count: {word_count}
Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}

Excerpt: {excerpt}

Review & Publish: {edit_url}

This post was saved as a draft. Open the link above to review and publish.
If you take no action, it stays as a draft.

— Coulisse Heir SEO Agent v3"""

    return {
        "subject": subject,
        "html_body": html_body,
        "text_body": text_body,
    }


def send_notification(email_data: dict, recipient: str = "") -> dict:
    """Send the notification email via Gmail SMTP."""
    import os
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    recipient = recipient or os.getenv("NOTIFICATION_EMAIL", "")
    gmail_user = os.getenv("GMAIL_USER", "")
    gmail_app_password = os.getenv("GMAIL_APP_PASSWORD", "")

    if not gmail_user or not gmail_app_password:
        logger.warning("GMAIL_USER or GMAIL_APP_PASSWORD not set — email not sent")
        return {"sent": False, "reason": "Gmail credentials not configured"}

    if not recipient:
        logger.warning("NOTIFICATION_EMAIL not set — email not sent")
        return {"sent": False, "reason": "No recipient email configured"}

    # Support multiple recipients (comma-separated)
    recipients = [r.strip() for r in recipient.split(",") if r.strip()]

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = email_data["subject"]
        msg["From"] = f"Coulisse Heir SEO Agent <{gmail_user}>"
        msg["To"] = ", ".join(recipients)

        msg.attach(MIMEText(email_data["text_body"], "plain"))
        msg.attach(MIMEText(email_data["html_body"], "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(gmail_user, gmail_app_password)
            server.sendmail(gmail_user, recipients, msg.as_string())

        logger.info(f"Email sent to {', '.join(recipients)} via Gmail")
        return {"sent": True, "recipients": recipients}

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"Gmail auth failed: {e}")
        return {"sent": False, "error": "Gmail authentication failed. Check GMAIL_APP_PASSWORD."}
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return {"sent": False, "error": str(e)}
