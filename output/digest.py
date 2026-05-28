import logging

logger = logging.getLogger(__name__)


def build_digest_html(surfaced_jobs: list[dict]) -> str:
    rows = ""
    for job in surfaced_jobs:
        missing = ", ".join(job.get("common_missing_keywords") or []) or "—"
        remote = "Yes" if job.get("remote") else "No"
        url = job.get("url", "")
        apply_link = f'<a href="{url}">Apply</a>' if url else "—"
        rows += f"""
        <tr>
          <td>{int((job.get('pass_rate') or 0) * 100)}%</td>
          <td>{int((job.get('ats_pass_rate') or 0) * 100)}%</td>
          <td>{job.get('title', '')}</td>
          <td>{job.get('company', '')}</td>
          <td>{job.get('location', '')}</td>
          <td>{remote}</td>
          <td>{missing}</td>
          <td>{job.get('sample_recruiter_reasoning', '')}</td>
          <td>{apply_link}</td>
        </tr>"""

    return f"""
    <html><body style="font-family:sans-serif;background:#fff;color:#222;padding:20px;">
    <h2>HeadHunter Daily Digest</h2>
    <p>{len(surfaced_jobs)} job(s) cleared the simulation threshold.</p>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;font-size:13px;width:100%;">
      <thead style="background:#f0f0f0;">
        <tr>
          <th>Pass</th><th>ATS</th><th>Title</th><th>Company</th>
          <th>Location</th><th>Remote</th><th>Missing Keywords</th>
          <th>Recruiter Take</th><th>Link</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    </body></html>"""


def send_digest(config: dict, surfaced_jobs: list[dict]) -> None:
    sg_cfg = config.get("sendgrid", {})
    if not sg_cfg.get("enabled"):
        return

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        html = build_digest_html(surfaced_jobs)
        message = Mail(
            from_email=sg_cfg.get("from_email"),
            to_emails=sg_cfg.get("to_email"),
            subject=f"HeadHunter: {len(surfaced_jobs)} surfaced job(s)",
            html_content=html,
        )
        sg = SendGridAPIClient(sg_cfg.get("api_key", ""))
        sg.send(message)
        logger.info("Digest sent to %s", sg_cfg.get("to_email"))
    except Exception as exc:
        logger.warning("Failed to send digest: %s", exc)
