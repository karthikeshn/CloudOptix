import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()

SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "dummy@example.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "dummy_password")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", SMTP_USERNAME)

def send_assignment_email(engineer_email: str, ticket_title: str, savings: str, ticket_id: int):
    """
    Sends an automated email to an engineer when a FinOps ticket is assigned to them.
    """
    if SMTP_USERNAME == "dummy@example.com":
        print(f"📧 [Email System] Simulation Mode: Email would be sent to {engineer_email} for Ticket #{ticket_id}")
        return False
        
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = engineer_email
        msg['Subject'] = f"🚀 New FinOps Ticket Assigned: {ticket_title}"

        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #4CAF50;">You have a new FinOps ticket!</h2>
            <p>Hello,</p>
            <p>You have been assigned a new optimization task to help reduce cloud waste.</p>
            <div style="background-color: #f9f9f9; padding: 15px; border-left: 4px solid #4CAF50; margin: 20px 0;">
                <strong>Ticket #{ticket_id}</strong>: {ticket_title}<br>
                <strong>Potential Savings</strong>: <span style="color: #4CAF50; font-weight: bold;">{savings}/month</span>
            </div>
            <p>Please log in to the FinOps Dashboard to view details and execute the deletion/optimization.</p>
            <br>
            <p>Best,<br>Your FinOps Robot 🤖</p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        print(f"📧 [Email System] Connecting to {SMTP_SERVER}...")
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        print(f"✅ [Email System] Successfully sent assignment email to {engineer_email}")
        return True
    except Exception as e:
        print(f"❌ [Email System] Failed to send email: {e}")
        return False
