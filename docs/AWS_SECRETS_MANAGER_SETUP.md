# AWS Secrets Manager Setup Guide

Hướng dẫn thiết lập External Secrets Operator với AWS Secrets Manager để quản lý Jenkins passwords một cách an toàn.

## Kiến trúc

```
AWS Secrets Manager → External Secrets Operator (ClusterSecretStore) → Kubernetes Secret → Jenkins Pod
```

## Prerequisites

- EKS cluster với OIDC provider enabled
- AWS CLI đã cấu hình
- kubectl access vào cluster
- External Secrets Operator đã được cài đặt

## Bước 1: Cài đặt External Secrets Operator

Nếu chưa cài, deploy qua ArgoCD:

```bash
kubectl apply -f apps/external-secrets/external-secrets-operator.yaml
```

Verify External Secrets Operator đã chạy:

```bash
kubectl get pods -n external-secrets
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=external-secrets -n external-secrets --timeout=300s
```

## Bước 2: Tạo Secrets trong AWS Secrets Manager

### Sử dụng AWS CLI:

```bash
# Set AWS region
export AWS_REGION="us-east-1"

# Tạo secret cho Staging
aws secretsmanager create-secret \
    --name jenkins/staging/admin-password \
    --description "Jenkins staging admin password" \
    --secret-string "your-secure-staging-password" \
    --region $AWS_REGION

# Tạo secret cho Production
aws secretsmanager create-secret \
    --name jenkins/production/admin-password \
    --description "Jenkins production admin password" \
    --secret-string "your-secure-production-password" \
    --region $AWS_REGION
```

### Hoặc sử dụng AWS Console:

1. Vào AWS Secrets Manager console
2. Click "Store a new secret"
3. Chọn "Other type of secret"
4. Nhập plaintext password
5. Secret name: `jenkins/staging/admin-password` hoặc `jenkins/production/admin-password`

## Bước 3: Setup IAM Role cho External Secrets

### 3.1 Tạo IAM Policy

Tạo file `iam-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": [
        "arn:aws:secretsmanager:*:*:secret:jenkins/*"
      ]
    }
  ]
}
```

Tạo policy:

```bash
aws iam create-policy \
    --policy-name ExternalSecretsPolicy \
    --policy-document file://iam-policy.json
```

### 3.2 Setup IRSA (IAM Roles for Service Accounts)

Lấy thông tin cluster:

```bash
export CLUSTER_NAME="your-eks-cluster-name"
export AWS_REGION="us-east-1"
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
```

Tạo IAM role với trust relationship:

```bash
eksctl create iamserviceaccount \
    --name external-secrets \
    --namespace external-secrets \
    --cluster $CLUSTER_NAME \
    --region $AWS_REGION \
    --attach-policy-arn arn:aws:iam::${AWS_ACCOUNT_ID}:policy/ExternalSecretsPolicy \
    --approve \
    --override-existing-serviceaccounts
```

Hoặc tạo thủ công:

```bash
# Get OIDC provider
OIDC_PROVIDER=$(aws eks describe-cluster --name $CLUSTER_NAME --region $AWS_REGION --query "cluster.identity.oidc.issuer" --output text | sed -e "s/^https:\/\///")

# Create trust policy
cat > trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/${OIDC_PROVIDER}"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "${OIDC_PROVIDER}:sub": "system:serviceaccount:external-secrets:external-secrets",
          "${OIDC_PROVIDER}:aud": "sts.amazonaws.com"
        }
      }
    }
  ]
}
EOF

# Create role
aws iam create-role \
    --role-name ExternalSecretsRole \
    --assume-role-policy-document file://trust-policy.json

# Attach policy
aws iam attach-role-policy \
    --role-name ExternalSecretsRole \
    --policy-arn arn:aws:iam::${AWS_ACCOUNT_ID}:policy/ExternalSecretsPolicy

# Annotate ServiceAccount
kubectl annotate serviceaccount external-secrets \
    -n external-secrets \
    eks.amazonaws.com/role-arn=arn:aws:iam::${AWS_ACCOUNT_ID}:role/ExternalSecretsRole \
    --overwrite
```

## Bước 4: Deploy ClusterSecretStore

ClusterSecretStore đã được cấu hình trong `charts/external-secrets/templates/external-secrets-clusterStore.yaml`.

Deploy external-secrets chart qua ArgoCD hoặc Helm:

```bash
# Via Helm
helm upgrade --install external-secrets ./charts/external-secrets \
    --namespace external-secrets \
    --create-namespace

# Verify ClusterSecretStore
kubectl get clustersecretstore
kubectl describe clustersecretstore aws-secrets-manager
```

## Bước 5: Deploy Jenkins với External Secrets

### Staging Environment

File `values-staging.yaml` đã được cấu hình:

```yaml
externalSecrets:
  enabled: true
  secretPath: "jenkins/staging/admin-password"
```

### Production Environment

File `values-prod.yaml` đã được cấu hình:

```yaml
externalSecrets:
  enabled: true
  secretPath: "jenkins/production/admin-password"
```

Deploy qua ArgoCD hoặc commit và push changes.

## Bước 6: Verify Deployment

### Kiểm tra ClusterSecretStore

```bash
kubectl get clustersecretstore aws-secrets-manager
kubectl describe clustersecretstore aws-secrets-manager
```

Status phải là `Valid`.

### Kiểm tra ExternalSecret

```bash
# Staging
kubectl get externalsecret -n jenkins-staging
kubectl describe externalsecret jenkins-server -n jenkins-staging

# Production
kubectl get externalsecret -n jenkins-production
kubectl describe externalsecret jenkins-server -n jenkins-production
```

Status phải là `SecretSynced`.

### Kiểm tra Secret đã được tạo

```bash
kubectl get secret jenkins-server -n jenkins-staging
kubectl get secret jenkins-server -n jenkins-staging -o jsonpath='{.data.jenkins-admin-password}' | base64 -d
```

### Kiểm tra Jenkins Pod

```bash
kubectl logs -n jenkins-staging -l app.kubernetes.io/name=jenkins -f
```

## Troubleshooting

### ExternalSecret shows "SecretSyncedError"

**Nguyên nhân:** IAM permissions không đúng hoặc secret không tồn tại.

**Giải pháp:**

```bash
# Kiểm tra logs của External Secrets Operator
kubectl logs -n external-secrets -l app.kubernetes.io/name=external-secrets

# Verify IAM role annotation
kubectl get sa external-secrets -n external-secrets -o yaml | grep eks.amazonaws.com/role-arn

# Test IAM permissions
aws secretsmanager get-secret-value --secret-id jenkins/staging/admin-password --region us-east-1
```

### ClusterSecretStore shows "Invalid"

**Nguyên nhân:** ServiceAccount không có IAM role annotation hoặc OIDC provider chưa được setup.

**Giải pháp:**

```bash
# Check ServiceAccount annotation
kubectl describe sa external-secrets -n external-secrets

# Verify OIDC provider
aws eks describe-cluster --name $CLUSTER_NAME --query "cluster.identity.oidc.issuer"

# Re-annotate ServiceAccount
kubectl annotate serviceaccount external-secrets \
    -n external-secrets \
    eks.amazonaws.com/role-arn=arn:aws:iam::${AWS_ACCOUNT_ID}:role/ExternalSecretsRole \
    --overwrite

# Restart External Secrets pods
kubectl rollout restart deployment external-secrets -n external-secrets
```

### Secret không được tạo

**Nguyên nhân:** ExternalSecret template configuration sai.

**Giải pháp:**

```bash
# Check ExternalSecret events
kubectl describe externalsecret jenkins-server -n jenkins-staging

# Manually trigger sync
kubectl delete externalsecret jenkins-server -n jenkins-staging
# ArgoCD sẽ tự động recreate
```

## Cập nhật Passwords

### Thay đổi password trong AWS Secrets Manager:

```bash
aws secretsmanager update-secret \
    --secret-id jenkins/staging/admin-password \
    --secret-string "new-secure-password" \
    --region us-east-1
```

External Secret sẽ tự động sync sau `refreshInterval` (mặc định: 1 giờ).

### Force sync ngay lập tức:

```bash
# Delete ExternalSecret (ArgoCD sẽ recreate)
kubectl delete externalsecret jenkins-server -n jenkins-staging

# Hoặc restart Jenkins pod để load password mới
kubectl rollout restart statefulset jenkins -n jenkins-staging
```

## Security Best Practices

### ✅ DO:

- ✅ Sử dụng strong passwords (ít nhất 16 ký tự, bao gồm chữ hoa, chữ thường, số, ký tự đặc biệt)
- ✅ Rotate passwords định kỳ (khuyến nghị: 90 ngày)
- ✅ Enable AWS Secrets Manager rotation
- ✅ Sử dụng IAM policies tối thiểu (least privilege)
- ✅ Enable AWS CloudTrail để audit
- ✅ Tag secrets properly trong AWS
- ✅ Sử dụng separate secrets cho mỗi environment
- ✅ Monitor External Secrets Operator logs

### ❌ DON'T:

- ❌ Commit passwords vào Git
- ❌ Share passwords giữa environments
- ❌ Sử dụng weak/default passwords
- ❌ Grant `secretsmanager:*` permissions
- ❌ Disable CloudTrail logging
- ❌ Hardcode AWS credentials
- ❌ Reuse passwords across services

## Cost Optimization

### AWS Secrets Manager Pricing (2024):

- **$0.40** per secret per month
- **$0.05** per 10,000 API calls

### Ước tính chi phí:

**Scenario 1: 2 environments (staging + production)**
- 2 secrets × $0.40 = **$0.80/month**
- API calls (với refreshInterval: 1h) = ~1,440 calls/month = **$0.01**
- **Total: ~$0.81/month**

**Scenario 2: Multi-environment (dev, staging, prod)**
- 3 secrets × $0.40 = **$1.20/month**
- API calls = ~2,160 calls/month = **$0.01**
- **Total: ~$1.21/month**

### Tips để giảm chi phí:

1. Tăng `refreshInterval` lên 6h hoặc 12h thay vì 1h
2. Sử dụng một secret có nhiều key/value pairs thay vì nhiều secrets
3. Xóa secrets không dùng

## Alternative: Local Development

Để local/dev environment không cần AWS:

```yaml
# values.yaml
externalSecrets:
  enabled: false  # Disable External Secrets

jenkins:
  adminPassword: "admin123"  # Local password only
```

Secret sẽ được tạo từ template `jenkins-secret.yaml` thay vì External Secrets.

## References

- [External Secrets Operator Documentation](https://external-secrets.io/)
- [AWS Secrets Manager Documentation](https://docs.aws.amazon.com/secretsmanager/)
- [EKS IRSA Documentation](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html)
