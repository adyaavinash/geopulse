Bicep IaC per docs/repo_structure_v1_azure.md "infra/" section, with one
change from the whiteboard: modules/postgres.bicep (Flexible Server B1ms,
pgvector allow-listed) replaces cosmos.bicep. monitoring.bicep's budget
alert is NOT optional — Azure has no automatic spend cap.
