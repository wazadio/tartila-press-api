import os
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType

conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_FROM=os.getenv("MAIL_FROM"),
    MAIL_FROM_NAME=os.getenv("MAIL_FROM_NAME", "Tartila Press"),
    MAIL_PORT=587,
    MAIL_SERVER="smtp.gmail.com",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
)

mail = FastMail(conf)


async def send_welcome_email(to: str, name: str):
    message = MessageSchema(
        subject="Welcome to Tartila Press!",
        recipients=[to],
        body=f"""
        <div style="font-family: Georgia, serif; max-width: 560px; margin: 0 auto; color: #1E1C2E;">
            <div style="background: #1D2B48; padding: 2rem; text-align: center;">
                <h1 style="color: #F0D898; margin: 0; font-size: 1.8rem;">📚 Tartila Press</h1>
            </div>
            <div style="padding: 2rem; background: #fff; border: 1px solid #E3DDD5;">
                <h2 style="color: #1D2B48;">Welcome, {name}!</h2>
                <p>Thank you for joining Tartila Press — Indonesia's home for great literature.</p>
                <p>You can now:</p>
                <ul>
                    <li>Browse our full book catalog</li>
                    <li>Explore our talented authors</li>
                    <li>Check out our publishing packages</li>
                </ul>
                <a href="{os.getenv('FRONTEND_URL', 'http://localhost:5173')}/books"
                   style="display:inline-block; margin-top:1rem; padding:0.75rem 1.5rem;
                          background:#B8913A; color:#fff; text-decoration:none;
                          border-radius:4px; font-weight:bold;">
                    Browse Books
                </a>
            </div>
            <div style="padding: 1rem; text-align: center; color: #6B6878; font-size: 0.8rem;">
                © {2024} Tartila Book Publisher. All rights reserved.
            </div>
        </div>
        """,
        subtype=MessageType.html,
    )
    await mail.send_message(message)


async def send_verification_email(to: str, name: str, verify_link: str):
    message = MessageSchema(
        subject="Verify your Tartila Press email",
        recipients=[to],
        body=f"""
        <div style="font-family: Georgia, serif; max-width: 560px; margin: 0 auto; color: #1E1C2E;">
            <div style="background: #1D2B48; padding: 2rem; text-align: center;">
                <h1 style="color: #F0D898; margin: 0; font-size: 1.8rem;">📚 Tartila Press</h1>
            </div>
            <div style="padding: 2rem; background: #fff; border: 1px solid #E3DDD5;">
                <h2 style="color: #1D2B48;">Hi {name}, please verify your email</h2>
                <p>Thanks for registering! Click the button below to verify your email address and activate your account.</p>
                <p>This link expires in <strong>24 hours</strong>.</p>
                <a href="{verify_link}"
                   style="display:inline-block; margin-top:1rem; padding:0.75rem 1.5rem;
                          background:#B8913A; color:#fff; text-decoration:none;
                          border-radius:4px; font-weight:bold;">
                    Verify Email
                </a>
                <p style="margin-top:1.5rem; color:#6B6878; font-size:0.85rem;">
                    If you didn't create an account, you can safely ignore this email.
                </p>
            </div>
            <div style="padding: 1rem; text-align: center; color: #6B6878; font-size: 0.8rem;">
                © 2024 Tartila Book Publisher. All rights reserved.
            </div>
        </div>
        """,
        subtype=MessageType.html,
    )
    await mail.send_message(message)


async def send_password_reset_email(to: str, name: str, reset_link: str):
    message = MessageSchema(
        subject="Reset your Tartila Press password",
        recipients=[to],
        body=f"""
        <div style="font-family: Georgia, serif; max-width: 560px; margin: 0 auto; color: #1E1C2E;">
            <div style="background: #1D2B48; padding: 2rem; text-align: center;">
                <h1 style="color: #F0D898; margin: 0; font-size: 1.8rem;">📚 Tartila Press</h1>
            </div>
            <div style="padding: 2rem; background: #fff; border: 1px solid #E3DDD5;">
                <h2 style="color: #1D2B48;">Password Reset</h2>
                <p>Hi {name}, we received a request to reset your password.</p>
                <p>Click the button below to set a new password. This link expires in <strong>1 hour</strong>.</p>
                <a href="{reset_link}"
                   style="display:inline-block; margin-top:1rem; padding:0.75rem 1.5rem;
                          background:#1D2B48; color:#fff; text-decoration:none;
                          border-radius:4px; font-weight:bold;">
                    Reset Password
                </a>
                <p style="margin-top:1.5rem; color:#6B6878; font-size:0.85rem;">
                    If you didn't request this, you can safely ignore this email.
                </p>
            </div>
            <div style="padding: 1rem; text-align: center; color: #6B6878; font-size: 0.8rem;">
                © 2024 Tartila Book Publisher. All rights reserved.
            </div>
        </div>
        """,
        subtype=MessageType.html,
    )
    await mail.send_message(message)


async def send_payment_invoice_email(
    to: str,
    name: str,
    transaction_id: int,
    package_name: str,
    total_amount: int,
    bank_name: str,
    bank_account_name: str,
    bank_account_number: str,
    payment_status: str,
):
    amount_text = f"Rp {int(total_amount):,}".replace(",", ".")
    message = MessageSchema(
        subject=f"Payment Invoice #{transaction_id} - Tartila Press",
        recipients=[to],
        body=f"""
        <div style="font-family: Georgia, serif; max-width: 560px; margin: 0 auto; color: #1E1C2E;">
            <div style="background: #1D2B48; padding: 2rem; text-align: center;">
                <h1 style="color: #F0D898; margin: 0; font-size: 1.8rem;">📚 Tartila Press</h1>
            </div>
            <div style="padding: 2rem; background: #fff; border: 1px solid #E3DDD5;">
                <h2 style="color: #1D2B48; margin-top: 0;">Payment Invoice</h2>
                <p>Hi {name}, your payment request has been recorded.</p>
                <table style="width:100%; border-collapse:collapse; margin:1rem 0; font-size:0.95rem;">
                    <tr><td style="padding:0.4rem 0; color:#6B6878;">Invoice ID</td><td style="padding:0.4rem 0; text-align:right; font-weight:700;">#{transaction_id}</td></tr>
                    <tr><td style="padding:0.4rem 0; color:#6B6878;">Package</td><td style="padding:0.4rem 0; text-align:right; font-weight:700;">{package_name}</td></tr>
                    <tr><td style="padding:0.4rem 0; color:#6B6878;">Payment Status</td><td style="padding:0.4rem 0; text-align:right; font-weight:700; text-transform:capitalize;">{payment_status}</td></tr>
                    <tr><td style="padding:0.4rem 0; color:#6B6878;">Total Amount</td><td style="padding:0.4rem 0; text-align:right; font-weight:700;">{amount_text}</td></tr>
                </table>
                <div style="margin-top:1rem; padding:0.9rem 1rem; border:1px dashed #C8C0B4; background:#F8F6F2;">
                    <div style="font-size:0.8rem; color:#6B6878; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:0.4rem;">Transfer To</div>
                    <div style="font-weight:700; color:#1D2B48;">{bank_name or '-'}</div>
                    <div style="font-weight:700; color:#1D2B48;">{bank_account_name or '-'}</div>
                    <div style="font-weight:700; color:#1D2B48;">{bank_account_number or '-'}</div>
                </div>
                <p style="margin-top:1.25rem; color:#6B6878; font-size:0.9rem;">
                    Please complete your transfer and keep your proof of payment.
                </p>
            </div>
            <div style="padding: 1rem; text-align: center; color: #6B6878; font-size: 0.8rem;">
                © 2024 Tartila Book Publisher. All rights reserved.
            </div>
        </div>
        """,
        subtype=MessageType.html,
    )
    await mail.send_message(message)
