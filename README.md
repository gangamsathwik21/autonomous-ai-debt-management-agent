# Autonomous AI Debt Management Agent

An AI-powered debt management system built using Python, LangGraph, FastAPI, Ollama and Streamlit. The application uses specialized agents to analyze customer financial information, validate payment records, evaluate repayment situations, prepare communication drafts and generate financial reports.

The system incorporates human approval before any communication can be authorized.

## Project Overview

Traditional debt management processes often involve repetitive customer analysis, payment tracking and communication preparation.

This project demonstrates a multi-agent architecture that automates several of these tasks while maintaining human oversight over customer communications.

### Key Features

- Multi-agent orchestration using LangGraph.
- Customer financial analysis.
- Payment history analysis.
- Automated financial data validation.
- Rule-based repayment decision-making.
- AI-assisted financial report generation.
- Communication draft generation.
- Human-in-the-loop approval mechanism.
- REST API backend using FastAPI.
- Interactive dashboard using Streamlit.
- Local LLM integration using Ollama.
- SQLite database integration.
- API key authentication.
- Docker-based deployment.
- Automated testing using Pytest.

## System Architecture

```text
              Streamlit Frontend
                      |
                      v
                FastAPI Backend
                      |
                      v
              LangGraph Workflow
                      |
          +-----------+-----------+
          |           |           |
          v           v           v
       Customer    Payment      Data
       Analysis    History    Validation
        Agent      Agent        Agent
          |           |           |
          +-----------+-----------+
                      |
                      v
                 Decision Agent
                      |
                      v
                Safety Checks
                      |
                      v
              Human Approval Gate
                      |
                      v
              Communication Agent
                      |
                      v
              Report Generation
                      |
                      v
                 SQLite Database
```

**LLM:** Ollama with Qwen 2.5 3B.

The LangGraph workflow coordinates the agents and controls the execution sequence. Communication generation is subject to validation and human approval.

## Specialized AI Agents

### 1. Customer Analysis Agent
Analyzes customer and loan information and generates a financial overview.

### 2. Payment History Agent
Evaluates successful, failed and pending payment records and calculates repayment metrics.

### 3. Data Validation Agent
Checks loan records, payment records, financial consistency and missing or invalid information.

### 4. Decision Agent
Uses rule-based logic to determine the next appropriate account-management action.

### 5. Communication Agent
Prepares customer communication drafts based on loan information and account status.

### 6. Report Generation Agent
Uses the local LLM to generate structured financial analysis reports based on available customer data.

## Human-in-the-Loop Mechanism

Customer communication drafts are not automatically sent.

The workflow checks validation results and decision requirements before generating a communication draft.

The approval system supports:

- Viewing pending communication drafts.
- Approving drafts.
- Rejecting drafts.
- Recording reviewer details.
- Maintaining approval history.

Actual SMS, email and telephone communication are not implemented.

## Technology Stack

| Category | Technologies |
|---|---|
| Programming Language | Python |
| Agent Orchestration | LangGraph |
| LLM | Ollama, Qwen 2.5 3B |
| LLM Integration | LangChain |
| Backend | FastAPI |
| Frontend | Streamlit |
| Database | SQLite |
| Data Processing | Pandas |
| Testing | Pytest, HTTPX |
| Containerization | Docker, Docker Compose |
| API Security | API Key Authentication |

## Project Structure

```text
AI-Debt-Management/
│
├── agents/
│   ├── customer_analysis.py
│   ├── payment_history.py
│   ├── decision_agent.py
│   ├── data_validation.py
│   ├── communication.py
│   └── report_generation.py
│
├── backend/
│   ├── api.py
│   └── database.py
│
├── frontend/
│   └── app.py
│
├── workflows/
│   └── debt_workflow.py
│
├── tests/
│   ├── conftest.py
│   ├── test_agents.py
│   ├── test_api.py
│   ├── test_database.py
│   ├── test_integration.py
│   └── additional agent and workflow tests
│
├── data/
│
├── .env.example
├── .gitignore
├── .dockerignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Installation and Setup

### Prerequisites

- Python 3.11
- Git
- Docker Desktop
- Ollama

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/autonomous-ai-debt-management-agent.git

cd autonomous-ai-debt-management-agent
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env.example` to `.env`.

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Generate your own API key and configure it in `.env`.

Example:

```env
DEBT_API_KEY=your_generated_secret_key
OLLAMA_BASE_URL=http://localhost:11434
```

Never commit your actual `.env` file.

### 5. Install and download the local LLM

Install Ollama and download the model:

```bash
ollama pull qwen2.5:3b
```

Ensure the Ollama service is running.

### 6. Start the FastAPI backend

```bash
uvicorn backend.api:app --reload --host 127.0.0.1 --port 8001
```

### 7. Start the Streamlit frontend

Open another terminal:

```bash
streamlit run frontend/app.py
```

Open the application:

```text
http://localhost:8501
```

Backend API:

```text
http://localhost:8001
```

API documentation:

```text
http://localhost:8001/docs
```

## Docker Deployment

The application supports containerized deployment using Docker Compose.

### 1. Configure `.env`

Ensure the project root contains a valid `.env` file with your API key.

### 2. Build Docker images

```bash
docker compose build
```

### 3. Start the containers

```bash
docker compose up -d
```

### 4. Check running containers

```bash
docker compose ps
```

### 5. Access the application

Frontend:

```text
http://localhost:8501
```

Backend:

```text
http://localhost:8001
```

Health check:

```text
http://localhost:8001/health
```

The Docker configuration connects the backend container to the Ollama service running on the host machine.

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | API status |
| GET | `/health` | Database health check |
| GET | `/customers` | Retrieve customers and loan details |
| GET | `/customers/{customer_id}` | Retrieve individual customer information |
| GET | `/agent-logs` | Retrieve agent execution logs |
| POST | `/analyze/{customer_id}` | Execute the debt management workflow |
| GET | `/communications/pending` | Retrieve pending communication drafts |
| POST | `/communications/{approval_id}/review` | Approve or reject a communication draft |
| GET | `/communications/history` | Retrieve communication approval history |

Protected endpoints require the `X-API-Key` header.

## Testing

The project uses Pytest for automated testing.

Run the complete test suite:

```bash
pytest -v
```

Run tests with coverage:

```bash
pytest --cov=agents --cov=backend --cov=workflows --cov-report=term-missing
```

The project has previously achieved **135 passing automated tests**.

## Current Project Scope and Limitations

This is an MVP and demonstration project.

- Uses synthetic customer and loan records.
- Uses a locally hosted Qwen 2.5 3B language model.
- Decision-making is primarily rule-based.
- Communication drafts require human approval.
- No actual SMS, email or telephone communication is sent.
- Does not currently implement predictive machine learning or RAG.
- Production-grade authentication, monitoring and infrastructure are future improvements.

## Future Enhancements

- Repayment risk prediction using machine learning.
- RAG-based financial knowledge retrieval.
- Integration with SMS and email services.
- Role-based access control.
- PostgreSQL database integration.
- Advanced analytics and monitoring.
- Cloud deployment.

## Author

Developed as an AI and Full-Stack Engineering project to explore multi-agent orchestration, LLM integration, backend development, workflow automation and human-in-the-loop systems.