# Azure Deployment

Deploy the email assistant as Azure Functions with timer-based ingestion and queue-based processing.

## Prerequisites

- Azure CLI (`az login`)
- Azure Functions Core Tools v4 (`func`)
- Python 3.11+

## Infrastructure

```bash
cd azure/infra
az group create --name rg-email-assistant --location eastus
az deployment group create \
  --resource-group rg-email-assistant \
  --template-file main.bicep \
  --parameters baseName=emailassistant
```

## Function App setup

1. Copy `function_app/local.settings.json.example` to `local.settings.json`.
2. Set `AzureWebJobsStorage` to your storage connection string.
3. Set `MSGRAPH_CLIENT_ID` and configure Graph API permissions on the app registration.
4. Ensure `AzureWebJobsFeatureFlags=EnableWorkerIndexing` is set (required for Python v2 model).

## Deploy

From the project root (so `app/` package is available):

```bash
# Symlink or copy app package into function_app if deploying standalone
func azure functionapp publish <function-app-name> --python
```

## Architecture

```
Timer (every 10 min)
    -> list Graph messages
    -> enqueue message IDs to email-processing queue

Queue trigger
    -> classify + match + draft
    -> write Azure Table metadata
    -> update Obsidian (if vault path configured)
    -> create Outlook draft (never auto-send)
```

## Auth in Azure

For production, migrate from device-code flow to:

- Managed Identity + `DefaultAzureCredential`
- App registration with application permissions for Mail.ReadWrite

Manual step: grant admin consent for Graph permissions in Azure Portal.

## Key Vault

Store secrets (`MSGRAPH_CLIENT_ID`, etc.) in Key Vault and reference them from Function App application settings.
