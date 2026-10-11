targetScope = 'resourceGroup'

@description('Azure region for all project resources.')
param location string = 'eastus'

@description('Short suffix for deployment naming. Resource names use the required Azure prefix and a subscription/resource-group/location unique token.')
@minLength(2)
@maxLength(12)
param environmentName string = 'test'

@description('Stable Kubernetes version returned by az aks get-versions for the selected region.')
param kubernetesVersion string

@description('Object ID of the deployment operator who needs Azure RBAC access to administer this AKS cluster.')
param deploymentPrincipalId string

var resourceToken = uniqueString(subscription().id, resourceGroup().id, location, environmentName)
var commonTags = {
  application: 'streamify'
  environment: environmentName
  managedBy: 'bicep'
}
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var eventHubsSenderRoleId = '2b629674-e913-4c01-ae53-ef4638d8f975'
var eventHubsReceiverRoleId = 'a638d3c7-ab3a-418d-83e6-5f17a39d4fde'
var blobContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'
var aksClusterAdminRoleId = 'b1ff04bb-8a4e-4dc4-8eb5-8693973ce19b'

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'azacr${resourceToken}'
  location: location
  tags: commonTags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource eventHubNamespace 'Microsoft.EventHub/namespaces@2024-01-01' = {
  name: 'azeh${resourceToken}'
  location: location
  tags: commonTags
  sku: {
    name: 'Standard'
    capacity: 1
  }
  properties: {
    minimumTlsVersion: '1.2'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource musicEvents 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: eventHubNamespace
  name: 'azehm${resourceToken}'
  properties: {
    messageRetentionInDays: 7
    partitionCount: 4
    status: 'Active'
  }
}

resource deadLetterEvents 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: eventHubNamespace
  name: 'azehd${resourceToken}'
  properties: {
    messageRetentionInDays: 7
    partitionCount: 4
    status: 'Active'
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2025-01-01' = {
  name: 'azst${resourceToken}'
  location: location
  tags: commonTags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Enabled'
    supportsHttpsTrafficOnly: true
  }
}

resource blobServices 'Microsoft.Storage/storageAccounts/blobServices@2025-01-01' = {
  parent: storage
  name: 'default'
}

resource archiveContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-01-01' = {
  parent: blobServices
  name: 'azct${resourceToken}'
  properties: {
    publicAccess: 'None'
  }
}

resource vault 'Microsoft.KeyVault/vaults@2024-11-01' = {
  name: 'azkv${resourceToken}'
  location: location
  tags: commonTags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: true
    publicNetworkAccess: 'Enabled'
  }
}

resource apiIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'azid${resourceToken}'
  location: location
  tags: commonTags
}

resource workerIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'azidw${resourceToken}'
  location: location
  tags: commonTags
}

resource aks 'Microsoft.ContainerService/managedClusters@2025-05-01' = {
  name: 'azaks${resourceToken}'
  location: location
  tags: commonTags
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'Base'
    tier: 'Free'
  }
  properties: {
    kubernetesVersion: kubernetesVersion
    dnsPrefix: 'streamify-${resourceToken}'
    supportPlan: 'KubernetesOfficial'
    oidcIssuerProfile: {
      enabled: true
    }
    securityProfile: {
      workloadIdentity: {
        enabled: true
      }
    }
    aadProfile: {
      managed: true
      enableAzureRBAC: true
    }
    addonProfiles: {
      azureKeyvaultSecretsProvider: {
        enabled: true
        config: {
          enableSecretRotation: 'true'
          rotationPollInterval: '2m'
        }
      }
    }
    agentPoolProfiles: [
      {
        name: 'sys'
        count: 2
        vmSize: 'Standard_D2as_v7'
        osDiskSizeGB: 64
        osDiskType: 'Managed'
        osType: 'Linux'
        osSKU: 'Ubuntu'
        type: 'VirtualMachineScaleSets'
        mode: 'System'
        enableAutoScaling: false
      }
    ]
    networkProfile: {
      networkPlugin: 'azure'
      networkPluginMode: 'overlay'
      networkPolicy: 'azure'
      loadBalancerSku: 'standard'
      outboundType: 'loadBalancer'
      serviceCidr: '10.0.0.0/16'
      dnsServiceIP: '10.0.0.10'
      podCidr: '10.244.0.0/16'
    }
    disableLocalAccounts: true
    enableRBAC: true
    publicNetworkAccess: 'Enabled'
  }
}

resource acrPullAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, aks.id, acrPullRoleId)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: aks.properties.identityProfile.kubeletidentity.objectId
    principalType: 'ServicePrincipal'
  }
}

resource eventSenderAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(eventHubNamespace.id, apiIdentity.id, eventHubsSenderRoleId)
  scope: eventHubNamespace
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', eventHubsSenderRoleId)
    principalId: apiIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource eventReceiverAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(eventHubNamespace.id, workerIdentity.id, eventHubsReceiverRoleId)
  scope: eventHubNamespace
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', eventHubsReceiverRoleId)
    principalId: workerIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource blobWriteAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, workerIdentity.id, blobContributorRoleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobContributorRoleId)
    principalId: workerIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource keyVaultSecretsUserAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, aks.id, keyVaultSecretsUserRoleId)
  scope: vault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalId: aks.properties.addonProfiles.azureKeyvaultSecretsProvider.identity.objectId
    principalType: 'ServicePrincipal'
  }
}

resource aksClusterAdminAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aks.id, deploymentPrincipalId, aksClusterAdminRoleId)
  scope: aks
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', aksClusterAdminRoleId)
    principalId: deploymentPrincipalId
    principalType: 'User'
  }
}

output resourceToken string = resourceToken
output aksName string = aks.name
output acrName string = registry.name
output acrLoginServer string = registry.properties.loginServer
output eventHubNamespace string = eventHubNamespace.name
output kafkaTopic string = musicEvents.name
output kafkaDlqTopic string = deadLetterEvents.name
output storageAccountName string = storage.name
output storageAccountUrl string = 'https://${storage.name}.blob.${environment().suffixes.storage}'
output storageContainer string = archiveContainer.name
output keyVaultName string = vault.name
output apiIdentityClientId string = apiIdentity.properties.clientId
output workerIdentityClientId string = workerIdentity.properties.clientId
output keyVaultProviderClientId string = aks.properties.addonProfiles.azureKeyvaultSecretsProvider.identity.clientId
