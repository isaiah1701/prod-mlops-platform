# AWS infrastructure

The platform is split into reusable Terraform modules and environment roots:

- `terraform/modules/ecr` creates immutable, scan-on-push image repositories. The environment creates one repository for the serving image and one for the training image.
- `terraform/modules/vpc` creates two-AZ public/private networking, NAT gateways, Kubernetes subnet tags, an S3 gateway endpoint, and private ECR, STS, and CloudWatch Logs endpoints.
- `terraform/modules/eks` creates an encrypted EKS cluster with audit logs, an EBS CSI driver role, explicit API access entries, and three managed node pools.
- `terraform/modules/route-53` uses the existing `5hort.site` hosted zone, DNS-validates a regional ACM certificate for the apex and wildcard domain, and accepts ALB alias records when ingress is added.

## Node-pool contract

The `system` pool hosts EKS add-ons. The `serving` and `training` pools are deliberately separate and tainted. A serving Deployment must select `workload=serving` and tolerate `workload=serving:NoSchedule`; a training Job must use the equivalent `training` selector and toleration. This prevents scheduled retraining workloads from consuming serving capacity.

Training defaults to CPU instances because this platform uses tabular models. Its desired size is zero in every environment to avoid paying for idle training nodes. Before scheduling a training Job, use a cluster autoscaler or scale that node group up through the deployment workflow. A GPU pool can be added later only if the chosen model genuinely needs it.

## State and deployment

Each environment has an empty S3 backend block. Bootstrap the encrypted state bucket and DynamoDB lock table once, then configure the backend without hard-coding account-specific names:

```sh
cd terraform/environments/dev
terraform init \
  -backend-config="bucket=<terraform-state-bucket>" \
  -backend-config="key=mlops/dev/terraform.tfstate" \
  -backend-config="region=eu-west-2" \
  -backend-config="dynamodb_table=<terraform-lock-table>" \
  -backend-config="encrypt=true"
terraform plan
```

The checked-in defaults are immediately usable for each environment; move to its corresponding directory for staging or production. If `platform_admin_principal_arn` is left unset, the Terraform caller receives the initial EKS administrator entry. Set it later for a stable human or CI administrator, and add extra `access_entries` or KMS administrators only when needed. The cluster API is private by default; turn on public access only with a restricted CIDR allow-list.
