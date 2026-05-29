@description('Short base name for resources (keep brief for storage account 24-char limit)')
param baseName string = 'ea'

@description('Azure region')
param location string = resourceGroup().location

@description('Python version for Function App')
param pythonVersion string = '3.11'

var uniqueSuffix = uniqueString(resourceGroup().id)
// Storage account: 3-24 chars, lowercase alphanumeric only
var storageAccountName = take('${baseName}st${uniqueSuffix}', 24)
var functionAppName = '${baseName}-func'
var appInsightsName = '${baseName}-ai'
var keyVaultName = take('${baseName}kv${uniqueSuffix}', 24)
var hostingPlanName = '${baseName}-plan'

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    accessPolicies: []
    enabledForDeployment: false
    enabledForTemplateDeployment: true
  }
}

// Flex Consumption avoids classic Dynamic (Y1) VM quota on some subscriptions
resource hostingPlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: hostingPlanName
  location: location
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  kind: 'functionapp'
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2023-01-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: hostingPlan.id
    siteConfig: {
      linuxFxVersion: 'Python|${pythonVersion}'
      appSettings: [
        {
          name: 'AzureWebJobsStorage'
          value: 'DefaultEndpointsProtocol=https;AccountName=${storage.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${storage.listKeys().keys[0].value}'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'python'
        }
        {
          name: 'AzureWebJobsFeatureFlags'
          value: 'EnableWorkerIndexing'
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'EMAIL_BACKEND'
          value: 'graph'
        }
        {
          name: 'CLASSIFIER_MODE'
          value: 'rule'
        }
        {
          name: 'AUTO_SEND_MODE'
          value: 'off'
        }
      ]
    }
    httpsOnly: true
  }
}

output functionAppName string = functionApp.name
output storageAccountName string = storage.name
output keyVaultName string = keyVault.name
output appInsightsName string = appInsights.name
