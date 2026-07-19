# Cloud-Reaper Security Architecture & IAM Policies

## Blast Radius Paranoia: Read-Only Default

Cloud-Reaper implements a strict **Dry-Run / Inform-Only Architecture** by default to prevent accidental resource modifications in production environments.

### Security Principles

1. **Read-Only by Default**: Initial setup uses ReadOnlyAccess/ViewOnlyAccess permissions
2. **Explicit Orchestration Toggle**: Active remediation requires explicit configuration
3. **Scoped Write Permissions**: Remediation uses separate IAM roles with minimal required permissions
4. **Audit Trail**: All actions are logged with SHA-256 cryptographic signatures

---

## Default IAM Policies (Read-Only)

### AWS: ReadOnlyAccess

The default AWS policy should be the managed `ReadOnlyAccess` policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "acm:Describe*",
        "acm:List*",
        "autoscaling:Describe*",
        "cloudformation:Describe*",
        "cloudformation:Get*",
        "cloudformation:List*",
        "cloudfront:Describe*",
        "cloudfront:Get*",
        "cloudfront:List*",
        "cloudtrail:Describe*",
        "cloudtrail:Get*",
        "cloudtrail:LookupEvents",
        "cloudwatch:Describe*",
        "cloudwatch:Get*",
        "cloudwatch:List*",
        "directconnect:Describe*",
        "dynamodb:Describe*",
        "dynamodb:List*",
        "ec2:Describe*",
        "ec2:Get*",
        "ecs:Describe*",
        "ecs:List*",
        "elasticache:Describe*",
        "elasticache:List*",
        "elasticbeanstalk:Describe*",
        "elasticbeanstalk:List*",
        "elasticloadbalancing:Describe*",
        "elasticloadbalancing:List*",
        "elastictranscoder:Describe*",
        "elastictranscoder:List*",
        "iam:List*",
        "iam:Get*",
        "kinesis:Describe*",
        "kinesis:List*",
        "opsworks:Describe*",
        "opsworks:List*",
        "rds:Describe*",
        "rds:List*",
        "redshift:Describe*",
        "redshift:List*",
        "route53:Describe*",
        "route53:Get*",
        "route53:List*",
        "s3:Describe*",
        "s3:Get*",
        "s3:List*",
        "sdb:Describe*",
        "sdb:List*",
        "ses:Describe*",
        "ses:List*",
        "sns:Describe*",
        "sns:List*",
        "sqs:Describe*",
        "sqs:List*",
        "storagegateway:Describe*",
        "storagegateway:List*",
        "sts:GetCallerIdentity"
      ],
      "Resource": "*"
    }
  ]
}
```

### Azure: Reader Role

The default Azure role should be the built-in `Reader` role:

```json
{
  "Name": "Reader",
  "Id": "acdd72a7-3385-48ef-bd42-f606fba81ae7",
  "Description": "Lets you view everything, but not make changes.",
  "Actions": [
    "*/read"
  ],
  "NotActions": [],
  "AssignableScopes": [
    "/"
  ]
}
```

### GCP: Viewer Role

The default GCP role should be the built-in `roles/viewer` role:

```yaml
# Viewer role includes:
# - compute.instances.get
# - compute.instances.list
# - compute.disks.get
# - compute.disks.list
# - storage.buckets.get
# - storage.buckets.list
# - billing.projects.get
```

---

## Remediation IAM Policies (Write-Access)

These policies should only be deployed when **explicitly enabling orchestration** via the `ENABLE_ORCHESTRATION=true` configuration.

### AWS: CloudReaperRemediationRole

Custom IAM policy with minimal required permissions for remediation:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:StopInstances",
        "ec2:ModifyInstanceAttribute",
        "ec2:TerminateInstances"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/CloudReaperManaged": "true"
        }
      }
    },
    {
      "Effect": "Allow",
      "Action": [
        "ec2:CreateTags",
        "ec2:DeleteTags"
      ],
      "Resource": "*"
    }
  ]
}
```

### Azure: CloudReaperRemediatorRole

Custom Azure role with minimal required permissions for remediation:

```json
{
  "Name": "Cloud-Reaper Remediator",
  "Description": "Minimal permissions for Cloud-Reaper cost optimization remediation",
  "Actions": [
    "Microsoft.Compute/virtualMachines/read",
    "Microsoft.Compute/virtualMachines/powerOff/action",
    "Microsoft.Compute/virtualMachines/deallocate/action",
    "Microsoft.Compute/virtualMachines/write",
    "Microsoft.Compute/disks/read",
    "Microsoft.Compute/disks/write",
    "Microsoft.Resources/subscriptions/resourceGroups/read"
  ],
  "NotActions": [
    "Microsoft.Compute/virtualMachines/delete",
    "Microsoft.Compute/disks/delete"
  ],
  "AssignableScopes": [
    "/subscriptions/{YOUR_SUBSCRIPTION_ID}"
  ]
}
```

### GCP: CloudReaperRemediatorRole

Custom GCP role with minimal required permissions for remediation:

```yaml
# Custom role with minimal permissions
title: "Cloud-Reaper Remediator"
description: "Minimal permissions for Cloud-Reaper cost optimization remediation"
stage: "GA"
includedPermissions:
- compute.instances.get
- compute.instances.list
- compute.instances.stop
- compute.instances.setMachineType
- compute.disks.get
- compute.disks.list
- compute.disks.update
- resourcemanager.projects.get
```

---

## Configuration Guide

### Step 1: Initial Setup (Read-Only)

Deploy Cloud-Reaper with default read-only permissions:

```bash
# .env configuration
DRY_RUN_MODE=true
ENABLE_REMEDIATION=false
ENABLE_ORCHESTRATION=false

# Use read-only IAM roles (Reader/Viewer/ReadOnlyAccess)
```

### Step 2: Review Recommendations

Run Cloud-Reaper in dry-run mode to review recommendations:

```bash
# Cloud-Reaper will scan and report optimization opportunities
# No changes will be made to your infrastructure
```

### Step 3: Enable Remediation (Optional)

If you want to enable active remediation:

1. **Deploy remediation-specific IAM role** using the policies above
2. **Update configuration** to enable remediation:

```bash
# .env configuration
DRY_RUN_MODE=false
ENABLE_REMEDIATION=true
ENABLE_ORCHESTRATION=false
```

3. **Restart Cloud-Reaper** with the new IAM role

### Step 4: Enable Orchestration (Advanced)

For automated execution of optimization schedules:

1. **Deploy orchestration-specific IAM role** with additional permissions
2. **Update configuration**:

```bash
# .env configuration
DRY_RUN_MODE=false
ENABLE_REMEDIATION=true
ENABLE_ORCHESTRATION=true
```

3. **Configure schedule** in the Cloud-Reaper dashboard

---

## Security Best Practices

1. **Never use root/admin credentials** for Cloud-Reaper
2. **Always start with read-only access** to understand your environment
3. **Review recommendations** before enabling remediation
4. **Use resource tagging** to scope remediation actions (e.g., `CloudReaperManaged=true`)
5. **Enable audit logging** to track all remediation actions
6. **Test in non-production** environments before production deployment
7. **Implement approval workflows** for automated remediation
8. **Regularly review IAM permissions** and apply principle of least privilege

---

## Audit Trail

Cloud-Reaper maintains a SHA-256 cryptographic audit trail of all actions:

```python
# Audit entries include:
- Action timestamp
- User/service principal
- Resource affected
- Action taken
- Previous state
- New state
- Cryptographic signature
```

This ensures tamper-proof logging of all remediation activities for compliance and security auditing.

---

## Troubleshooting

### Remediation Actions Not Executing

If remediation actions are not executing despite being enabled:

1. Check `ENABLE_REMEDIATION` is set to `true`
2. Check `DRY_RUN_MODE` is set to `false`
3. Verify IAM role has the required write permissions
4. Check Cloud-Reaper logs for permission errors

### Permission Errors

If you encounter permission errors:

1. Verify the correct IAM role is assigned
2. Check the role includes the required actions
3. Ensure resource tagging conditions are met
4. Review Azure/AWS/GCP IAM policy syntax

---

## Support

For security-related questions or issues:

- Review the main [README.md](../README.md)
- Check the [Documentation Hub](README.md)
- Open a GitHub issue with security details redacted