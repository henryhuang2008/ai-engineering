# 🤖 CRM Agent Tutorial - Ralph the Marketing AI

Welcome to the **CRM Agent Tutorial**! This project demonstrates how to build an intelligent Customer Relationship Management (CRM) system using AI agents, LangGraph, and real customer data. Meet **Ralph** - your AI-powered marketing assistant who can analyze customer behavior, create personalized marketing campaigns, and automate email communications.

## 🎯 What You'll Learn

- Build an AI agent using **LangGraph** and **OpenAI**
- Implement **human-in-the-loop** workflows for sensitive operations
- Create **RFM (Recency, Frequency, Monetary) analysis** for customer segmentation
- Design **personalized marketing campaigns** using AI
- Integrate **PostgreSQL** with AI agents for real-time data analysis
- Use **Model Context Protocol (MCP)** for tool integration

## 🏗️ Project Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Ralph Agent   │    │   Database      │
│   (Chat UI)     │◄──►│   (LangGraph)   │◄──►│   (PostgreSQL)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │  MCP Marketing  │
                       │     Server      │
                       └─────────────────┘
```

## 🚀 Features

- **🧠 Intelligent Customer Analysis**: Ralph analyzes customer purchase history and behavior patterns
- **📧 Personalized Email Campaigns**: Creates targeted marketing emails with customer-specific content
- **🎯 Customer Segmentation**: Uses RFM analysis to categorize customers (Champions, At Risk, etc.)
- **✋ Human Approval**: Requires human review for sensitive actions like sending campaigns
- **📊 Real-time Data**: Works with actual retail transaction data
- **🔄 Campaign Types**:
  - **Re-engagement**: Win back inactive customers
  - **Referral**: Leverage high-value customers for referrals
  - **Loyalty**: Thank and retain valuable customers

## 📋 Prerequisites

Before you begin, ensure you have:

- **Python 3.13+** installed
- **PostgreSQL** database (we'll use Supabase)
- **OpenAI API key**
- **Git** for cloning the repository

## ⚡ Quick Start

Want to get started immediately? Here's the fastest path:

This project uses `uv` for dependency management. If you don't have `uv` installed, follow the instructions [here](https://docs.astral.sh/uv/guides/install-python/).

1. **Clone and setup**:
   ```bash
   git clone <your-repo-url>
   cd crm-agent
   uv sync  # Install dependencies
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your OpenAI API key and Supabase URI
   ```

3. **Setup database** (create free Supabase account at [supabase.com](https://supabase.com)):
   - Create a new Supabase project. Use the generate_password feature to generate a secure password, copy it into the .env file for use later.
   - Copy the connection string from the Supabase project settings and paste it into the .env file (you'll see a 'connect' button at the top of the dashboard), replacing the placeholder with the actual connection string.
   - Replace the password placeholder with the password you generated earlier.
   - Copy and paste the sql from `db/migration-create-tables.sql` into the Supabase SQL editor. This will automatically create all of the db tables for you.
   - Import each CSV file from the `data` directory into the corresponding table in Supabase.

4. **Verify and run**:
   ```bash
   cd frontend && uv run python chat_local.py  # Start chatting with Ralph!
   ```

## 🎮 Running the Application

### Start the Chat Interface

```bash
cd frontend
uv run python chat_local.py
```

You should see Ralph introduce himself:

```
---- 🤖 Assistant ----

Hi there! I'm Ralph, your customer service agent and marketing expert. I'm here to help you understand your customers better and create targeted marketing campaigns that drive results.

I have access to your CRM database with customer information, transaction history, and RFM analysis. I can help you:

🎯 Analyze customer behavior and segments
📧 Create personalized marketing campaigns
📊 Generate insights from your customer data
✉️ Send targeted emails to specific customer groups

What would you like to work on today?
```

### Example Interactions

Try these commands to see Ralph in action:

1. **Customer Analysis**:
   ```
   "Show me our top 5 customers by total spending"
   ```

2. **Segment Analysis**:
   ```
   "How many customers do we have in each RFM segment?"
   ```

3. **Create a Campaign**:
   ```
   "Create a re-engagement campaign for customers who haven't purchased in the last 6 months"
   ```

4. **Send Personalized Emails**:
   ```
   "Send a loyalty email to our champion customers thanking them for their business"
   ```

## 📊 Understanding the Data

### Customer Segments (RFM Analysis)

Ralph uses RFM analysis to categorize customers:

- **🏆 Champions** (555): Best customers - high recency, frequency, and monetary value
- **🆕 Recent Customers** (5XX): Recently active customers
- **🔄 Frequent Buyers** (X5X): Customers who buy often
- **💰 Big Spenders** (XX5): High-value customers
- **⚠️ At Risk** (1XX): Haven't purchased recently
- **👥 Others**: Everyone else

### Database Schema

The project includes these main tables:

- **customers**: Customer information and contact details
- **transactions**: Purchase history and transaction data
- **items**: Product catalog with descriptions and prices
- **rfm**: Customer segmentation scores
- **marketing_campaigns**: Campaign tracking
- **campaign_emails**: Email delivery and engagement tracking

## Adding New Tools

Create new MCP tools in `src/ralph/mymcp/servers/marketing_server.py`:

```python
@mcp.tool()
async def your_new_tool(param: str) -> str:
    """Your tool description."""
    # Your implementation here
    return "Tool result"
```

## 📚 Learning Resources

### Key Concepts Covered

- **LangGraph**: Framework for building stateful AI agents
- **MCP (Model Context Protocol)**: Standard for AI tool integration
- **RFM Analysis**: Customer segmentation methodology
- **Human-in-the-loop**: AI systems with human oversight
- **PostgreSQL**: Relational database for customer data

### Recommended Reading

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [RFM Analysis Guide](https://en.wikipedia.org/wiki/RFM_(market_research))
- [OpenAI API Documentation](https://platform.openai.com/docs)

## 🤝 Contributing

This is a tutorial project, but contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

**Happy Learning! 🚀**

If you found this tutorial helpful, please ⭐ star the repository and subscribe to the [YouTube channel](https://www.youtube.com/@KennethLiao) for more AI tutorials!
