from mcp.server.fastmcp import FastMCP
from sqlalchemy import text
import os
import pandas as pd
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from uuid import UUID

load_dotenv()


# ----------------------------
# DB Session
# ----------------------------

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(url=os.getenv("SUPABASE_URI"))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ----------------------------
# MCP Server
# ----------------------------

mcp = FastMCP("marketing")


async def send_email_via_mcp(
    recipient_email: str,
    subject: str,
    body: str,
    campaign_id: UUID,
    customer_id: int,
) -> None:
    """Send one email using the Resend MCP server."""
    api_key = os.getenv("RESEND_API_KEY")
    sender_email = os.getenv("SENDER_EMAIL_ADDRESS")
    if not api_key or not sender_email:
        raise RuntimeError(
            "RESEND_API_KEY and SENDER_EMAIL_ADDRESS must be configured"
        )

    client = MultiServerMCPClient(
        connections={
            "resend": {
                "command": "npx",
                "args": ["-y", "resend-mcp"],
                "transport": "stdio",
                "env": {
                    "RESEND_API_KEY": api_key,
                    "SENDER_EMAIL_ADDRESS": sender_email,
                },
            }
        },
        handle_tool_errors=False,
    )
    tools = await client.get_tools()
    send_tool = next((tool for tool in tools if tool.name == "send-email"), None)
    if send_tool is None:
        raise RuntimeError("The Resend MCP server does not provide send-email")

    await send_tool.ainvoke(
        {
            "to": [recipient_email],
            "subject": subject,
            "text": body,
            "idempotencyKey": f"{campaign_id}:{customer_id}",
        }
    )


@mcp.tool()
async def create_campaign(
    name: str,
    type: str,
    description: str,
) -> str:
    """Create a marketing campaign.
    
    Args:
        name: The name of the campaign.
        type: The type of the campaign. One of: loyalty, referral, re-engagement
        description: The description of the campaign.

    Returns:
        The ID of the created campaign.
    """
    with SessionLocal() as session:
        result = session.execute(
            text(
                """
                INSERT INTO marketing_campaigns (name, type, description)
                VALUES (:name, :type, :description)
                RETURNING id
                """
            ),
            {"name": name, "type": type, "description": description},
        )
        session.commit()
        return str(result.fetchone()[0])

@mcp.tool()
async def send_campaign_email(
    campaign_id: UUID,
    customer_id: int,
    subject: str,
    body: str,
) -> str:
    """Send a campaign email.
    
    Args:
        campaign_id: The ID of the campaign.
        customer_id: The ID of the customer.
        subject: The subject of the email.
        body: The body of the email.

    Returns:
        A confirmation that the email was sent.
    """
    with SessionLocal() as session:
        recipient_email = session.execute(
            text('SELECT "Email" FROM customers WHERE "Customer ID" = :customer_id'),
            {"customer_id": customer_id},
        ).scalar_one_or_none()

    if not recipient_email:
        raise ValueError(f"No email address found for customer {customer_id}")

    await send_email_via_mcp(
        recipient_email,
        subject,
        body,
        campaign_id,
        customer_id,
    )

    with SessionLocal() as session:
        session.execute(
            text(
                """
                INSERT INTO campaign_emails (campaign_id, customer_id, subject, body)
                VALUES (:campaign_id, :customer_id, :subject, :body)
                """
            ),
            {"campaign_id": campaign_id, "customer_id": customer_id, "subject": subject, "body": body},
        )
        session.commit()

    return f"Successfully sent <{subject}> to customer <{customer_id}>!"


if __name__ == "__main__":
    mcp.run(transport="stdio")
