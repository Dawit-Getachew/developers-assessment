# WorkLog Settlement System

## Assessment Task

You're building a backend feature for a system that compensates independent workers based on time they've reported against tasks. Time is not reported as a single value but as **multiple independently recorded segments**, each of which may later be questioned, removed, or adjusted. The container representing all work done against a task is called a **WorkLog**.

Workers are not paid per task or per time segment. Instead, at the end of every month, the system performs a **settlement run** that calculates how much a worker should receive for all eligible work within a given period and attempts to issue a single payout. Let's call this single payout a **Remittance**.

However, the system must support the fact that **historical financial data is not immutable**.

### Key Constraints

The system must correctly handle the following realities:

1. **Work can evolve after payment**
   - Additional time segments may be recorded against previously settled work.

2. **Adjustments can be retroactive**
   - Quality issues or disputes may result in deductions that can be applied to both work that was already settled in the past or yet to be settled work.

3. **Settlement attempts are not guaranteed to succeed**
   - A payout attempt may fail or be explicitly cancelled.

You are expected to design a solution that preserves **financial correctness over time**, even as data continues to change.

### Expected Endpoints

1. **`/generate-remittances-for-all-users`**
   - Generates remittances for all users based on eligible work.

2. **`/list-all-worklogs`**
   - Lists all worklogs with filtering and amount information.
   - **Query Parameters:**
     - `remittanceStatus`: Filter by remittance status. Accepts `REMITTED` or `UNREMITTED`.
   - **Response:** Must include the amount per worklog.

## Setup Instructions

To start development, simply run:

```bash
docker compose up
```

This will start all required services including the backend API, database, and any other dependencies. Once the services are up, you can access:

- **API Documentation:** `http://localhost:8000/docs`
- **Backend API:** `http://localhost:8000`

## Assessment Submission Process

To submit your assessment, please follow these steps:

1. **Fork this repository**
   - Create a fork of this repository to your personal GitHub account.

2. **Raise a Pull Request**
   - Create a Pull Request from your personal fork back to this repository.

3. **Required Documentation**
   Your PR must include:
   
   a. **DBML Diagram**
      - Include a DBML (Database Markup Language) diagram of the table schema you used to solve this problem.
      - Save it as `schema.dbml` in the root directory or include it in your PR description.
   
   b. **Sample API Responses**
      - Include a JSON file showing sample responses from both endpoints.
      - You can obtain these sample responses from the `/docs` endpoint on your backend server, after you've implemented the solution.
      - Save it as `sample-responses.json` in the root directory or include it in your PR description.

### Submission Checklist

- [ ] Forked the repository
- [ ] Implemented both required endpoints
- [ ] Added DBML diagram of your database schema
- [ ] Added JSON file with sample responses from both endpoints
- [ ] Created Pull Request


## Technology Stack

This project uses:

- **FastAPI** - Python backend framework
- **SQLModel** - SQL database ORM
- **PostgreSQL** - Database
- **Docker Compose** - Container orchestration

