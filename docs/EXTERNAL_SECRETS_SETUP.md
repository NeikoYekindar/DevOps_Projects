# External Secrets Setup Guide

This guide explains how to deploy Jenkins with AWS Secrets Manager integration using External Secrets Operator.

## Architecture

```
AWS Secrets Manager → External Secrets Operator → Kubernetes Secret → Jenkins Pod
```

## Prerequisites

- EKS cluster with OIDC provider enabled
- AWS CLI configured
- kubectl access to cluster
- Helm 3.x

## Step-by-Step Deployment

### 1. Deploy External Secrets Operator

Deploy via ArgoCD:

```bash
kubectl apply -f apps/external-secrets/external-secrets-operator.yaml
```

Wait for the operator to be ready:

```bash
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=external-secrets -n external-secrets --timeout=300s
```

### 2. Create Secrets in AWS Secrets Manager

Edit the script to set your region and passwords:

```bash
# Edit the script first
nano scripts/create-aws-secrets.sh

# Run the script
chmod +x scripts/create-aws-secrets.sh
./scripts/create-aws-secrets.sh
```

Or create manually:

```bash
# Staging
aws secretsmanager create-secret \
    --name jenkins/staging/admin-password \
    --secret-string "your-secure-password" \
    --region us-east-1

# Production
aws secretsmanager create-secret \
    --name jenkins/production/admin-password \
    --secret-string "your-secure-password" \
    --region us-east-1
```

### 3. Setup IAM Role and Policy

Edit the script to set your EKS cluster name:

```bash
# Edit the script first
nano scripts/setup-iam-role.sh

# Run the script
chmod +x scripts/setup-iam-role.sh
./scripts/setup-iam-role.sh
```

This script will:
- Create IAM policy with SecretsManager read permissions
- Create IAM role with OIDC trust relationship
- Annotate the External Secrets ServiceAccount

### 4. Deploy Jenkins

The External Secrets configuration is already set in values files:

**Staging** ([values-staging.yaml](../charts/jenkins/values-staging.yaml)):
```yaml
externalSecrets:
  enabled: true
  secretPath: "jenkins/staging/admin-password"
```

**Production** ([values-prod.yaml](../charts/jenkins/values-prod.yaml)):
```yaml
externalSecrets:
  enabled: true
  secretPath: "jenkins/production/admin-password"
```

Deploy via ArgoCD or commit and push your changes.

### 5. Verify Deployment

Check External Secret status:

```bash
# For staging
kubectl get externalsecret -n jenkins-staging
kubectl describe externalsecret jenkins-server -n jenkins-staging

# For production
kubectl get externalsecret -n jenkins-production
kubectl describe externalsecret jenkins-server -n jenkins-production
```

Check if Secret was created:

```bash
kubectl get secret jenkins-server -n jenkins-staging
```

Check Jenkins pod logs:

```bash
kubectl logs -n jenkins-staging -l app.kubernetes.io/name=jenkins -f
```

## Troubleshooting

### ExternalSecret shows "SecretSyncedError"

Check IAM role permissions:

```bash
kubectl describe externalsecret jenkins-server -n jenkins-staging
```

Verify ServiceAccount annotation:

```bash
kubectl get sa external-secrets -n external-secrets -o yaml | grep eks.amazonaws.com/role-arn
```

### Secret not created

Check External Secrets Operator logs:

```bash
kubectl logs -n external-secrets -l app.kubernetes.io/name=external-secrets
```

### AWS Secrets Manager access denied

Verify IAM policy is attached to role:

```bash
aws iam list-attached-role-policies --role-name ExternalSecretsRole
```

## Updating Passwords

To update password in AWS Secrets Manager:

```bash
aws secretsmanager update-secret \
    --secret-id jenkins/staging/admin-password \
    --secret-string "new-password" \
    --region us-east-1
```

The External Secret will automatically sync (default: every 1 hour).

To force immediate sync, delete and recreate the ExternalSecret:

```bash
kubectl delete externalsecret jenkins-server -n jenkins-staging
# ArgoCD will recreate it automatically
```

## Security Best Practices

✅ **DO:**
- Use strong, unique passwords for each environment
- Rotate passwords regularly
- Use AWS Secrets Manager rotation features
- Restrict IAM permissions to specific secret paths
- Enable AWS CloudTrail for audit logging

❌ **DON'T:**
- Commit passwords to Git
- Share passwords between environments
- Use default/weak passwords
- Grant excessive IAM permissions

## Cost Considerations

AWS Secrets Manager pricing (as of 2024):
- $0.40 per secret per month
- $0.05 per 10,000 API calls

For 2 secrets (staging + production):
- Monthly cost: ~$0.80 + API calls

## Alternative: Local Development

For local/dev environments where you don't need AWS integration:

```yaml
# values.yaml
externalSecrets:
  enabled: false  # Disable External Secrets

jenkins:
  adminPassword: "admin123"  # Use hardcoded password for local only
```

This will create a regular Kubernetes Secret instead of using External Secrets.
