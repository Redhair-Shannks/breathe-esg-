# Submission Checklist

## Before Submitting

- Push this repository to GitHub.
- Deploy with Render using `render.yaml`.
- Confirm the deployed app opens at the Render URL.
- Confirm the prototype dashboard opens without app login.
- Confirm optional Django admin login works if you plan to share it:
  - username: `analyst@demo.local`
  - password: `demo-password`
- Confirm seeded rows appear in the dashboard.
- Upload each file in `sample_data/` once on the deployed app if the seed command did not run.
- Open `MODEL.md`, `DECISIONS.md`, `TRADEOFFS.md`, and `SOURCES.md` in GitHub and make sure they render cleanly.

## Repository Access

Share the GitHub repository with:

- saurav@breatheesg.com
- rahul@breatheesg.com
- shivang@breatheesg.com

## Submission Email Shape

Subject: Tech Intern Assignment - Breathe ESG

Body:

```text
Hi,

Here is my submission for the Breathe ESG tech intern assignment.

GitHub repository: <repo link>
Deployed app: <live app link>

Dashboard access:
No app login required for the prototype.

Optional Django admin credentials:
Username: analyst@demo.local
Password: demo-password

I focused the prototype on ingestion lineage, normalization, validation issues, analyst review, approval lock, and audit trail. The required MODEL.md, DECISIONS.md, TRADEOFFS.md, and SOURCES.md files are included in the repository.

Thanks,
<your name>
```

## Defense Notes

Core sentence:

```text
I optimized for source lineage and analyst/audit review, not broad fake integration coverage. CSV upload is only the transport in this prototype; the model already separates raw source records from normalized activity records so SAP OData, Green Button Connect, or Concur API pulls can feed the same pipeline later.
```
