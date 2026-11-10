import logging
from html import escape

import resend
from django.conf import settings

logger = logging.getLogger(__name__)

NOT_AVAILABLE = "Not available"

PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
</head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:30px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

          <!-- Header -->
          <tr>
            <td style="background:#ac1c7a;padding:28px 40px;text-align:center;">
              <span style="color:#ffffff;font-size:22px;font-weight:bold;letter-spacing:1px;">Noorrix Motors</span>
            </td>
          </tr>

          <!-- Title -->
          <tr>
            <td style="padding:32px 40px 8px;text-align:center;">
              <h2 style="margin:0;color:#ac1c7a;font-size:22px;">{title}</h2>
              <p style="margin:8px 0 0;color:#888;font-size:14px;">{intro}</p>
            </td>
          </tr>

          <!-- Details Table -->
          <tr>
            <td style="padding:24px 40px;">
              <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
                {rows}
              </table>
            </td>
          </tr>

          {extra}

          <!-- Footer -->
          <tr>
            <td style="background:#ac1c7a;padding:16px 40px;text-align:center;">
              <p style="margin:0;color:#ffffff;font-size:12px;">&copy; Noorrix Motors &mdash; This email was generated automatically.</p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

ROW_TEMPLATE = (
    '<tr style="background:{background};">'
    '<td style="padding:12px 16px;font-weight:bold;color:#555;font-size:14px;width:30%;border-bottom:1px solid #eee;vertical-align:top;">{label}</td>'
    '<td style="padding:12px 16px;color:#222;font-size:14px;border-bottom:1px solid #eee;white-space:pre-line;">{value}</td>'
    "</tr>"
)

PHOTOS_TEMPLATE = """
          <!-- Photos -->
          <tr>
            <td style="padding:0 40px 24px;">
              <p style="margin:0 0 12px;color:#555;font-size:14px;font-weight:bold;">Photos (click to open full size)</p>
              {links}
            </td>
          </tr>
"""

PHOTO_TEMPLATE = (
    '<a href="{url}" style="display:inline-block;margin:0 8px 8px 0;">'
    '<img src="{url}" alt="Car photo" width="150" style="width:150px;border-radius:4px;border:1px solid #eee;" />'
    "</a>"
)

NEXT_STEPS_TEMPLATE = """
          <!-- Next steps -->
          <tr>
            <td style="padding:0 40px 32px;">
              <p style="margin:0;color:#333;font-size:15px;line-height:1.6;">
                Our team will review your details and photos, then email you with an offer.
                If you need anything in the meantime, just reply to this email.
              </p>
            </td>
          </tr>
"""


def send_enquiry_emails(enquiry, image_urls):
    """Runs in a background thread, so it must not touch the database."""
    _send_owner_email(enquiry, image_urls)
    _send_customer_email(enquiry)


def _send_owner_email(enquiry, image_urls):
    if not settings.ADMIN_EMAIL:
        logger.warning("ADMIN_EMAIL not configured, skipping owner email for sell my car enquiry %s", enquiry.pk)
        return

    try:
        html_body = PAGE_TEMPLATE.format(
            title="New Sell My Car Enquiry",
            intro="A customer wants to sell their car. Reply to this email to send your offer.",
            rows=_render_rows(_owner_rows(enquiry)),
            extra=_render_photos(image_urls),
        )
        resend.api_key = settings.RESEND_API_KEY
        resend.Emails.send({
            "from": settings.DEFAULT_FROM_EMAIL,
            "to": [settings.ADMIN_EMAIL],
            "reply_to": [enquiry.email],
            "subject": f"[Sell My Car] {enquiry.reg} {enquiry.car_label}".strip(),
            "html": html_body,
        })
        logger.info("Owner email sent for sell my car enquiry %s", enquiry.pk)
    except Exception as exc:
        logger.error("Owner email failed for sell my car enquiry %s: %s", enquiry.pk, exc, exc_info=True)


def _send_customer_email(enquiry):
    try:
        rows = [("Registration", enquiry.reg)]
        if enquiry.car_label:
            rows.append(("Car", enquiry.car_label))
        rows += [
            ("Mileage", _format_mileage(enquiry)),
            ("Inspection", _format_slot(enquiry)),
        ]

        html_body = PAGE_TEMPLATE.format(
            title="Enquiry received",
            intro=f"Thanks {escape(enquiry.name)}, we've received the details of your car.",
            rows=_render_rows(rows),
            extra=NEXT_STEPS_TEMPLATE,
        )
        resend.api_key = settings.RESEND_API_KEY
        resend.Emails.send({
            "from": settings.DEFAULT_FROM_EMAIL,
            "to": [enquiry.email],
            "subject": "We've received your enquiry — Noorrix Motors",
            "html": html_body,
        })
        logger.info("Customer email sent for sell my car enquiry %s", enquiry.pk)
    except Exception as exc:
        logger.error("Customer email failed for sell my car enquiry %s: %s", enquiry.pk, exc, exc_info=True)


def _owner_rows(enquiry):
    return [
        ("Registration", enquiry.reg),
        ("Make", enquiry.make or NOT_AVAILABLE),
        ("Model", enquiry.model or NOT_AVAILABLE),
        ("Mileage", _format_mileage(enquiry)),
        ("Name", enquiry.name),
        ("Email", enquiry.email),
        ("Phone", enquiry.phone),
        ("Address", enquiry.address),
        ("Message", enquiry.message or "None"),
        ("Inspection", _format_slot(enquiry)),
    ]


def _render_rows(rows):
    """Every value goes through escape here, as customers can type anything."""
    return "".join(
        ROW_TEMPLATE.format(
            background="#f9f9f9" if index % 2 == 0 else "#ffffff",
            label=escape(label),
            value=escape(str(value)),
        )
        for index, (label, value) in enumerate(rows)
    )


def _render_photos(image_urls):
    if not image_urls:
        return ""
    links = "".join(PHOTO_TEMPLATE.format(url=escape(url)) for url in image_urls)
    return PHOTOS_TEMPLATE.format(links=links)


def _format_mileage(enquiry):
    return f"{enquiry.mileage:,} miles"


def _format_slot(enquiry):
    date = enquiry.appointment_date
    return f"{date:%A} {date.day} {date:%B %Y} at {enquiry.appointment_time:%H:%M} (UK time)"
