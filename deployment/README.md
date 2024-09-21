# Backend Infra Terraform Setup Guide

This guide provides instructions on how to set up your AWS environment using Terraform.

## Prerequisites

Before you begin, ensure you have the following installed:

- AWS CLI: Follow the instructions [here](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html#getting-started-install-instructions) to install and configure the AWS CLI.
- Terraform: Install Terraform for your system from [here](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli?source=post_page-----752afd44df8e--------------------------------#install-terraform).

## Configuration

Update the `main.tf` file with the correct AWS region, path to your AWS credential files, and your AWS CLI profile.

## Initialization

Initialize Terraform by running the following command in your terminal:

```bash
terraform init
```

## Workspaces

Create and manage Terraform workspaces for different environments, kinda like python virtual environments:

```bash
terraform workspace new staging
terraform workspace new production
```

Ensure you're in the correct workspace before deploying:

```bash
terraform workspace select staging  # For staging environment
```

## Deployment

Execute the following commands in order to format, validate, plan, and deploy your infrastructure:

```bash
terraform fmt          # Formats the Terraform files
terraform validate     # Validates the Terraform configuration
terraform plan         # Shows a plan of the changes to be made
terraform apply        # Applies the changes and deploys resources
```

## Destruction

To destroy all resources managed by Terraform, use:

```bash
terraform destroy
```

**Note:** Run all the Terraform commands from within the `deployment/` directory.

## Additional Resources

For a detailed explanation of the file structure and a deeper understanding of the setup, please read this ADR:

- [ADR: New Quiz Backend on EC2](https://www.notion.so/avantifellows/ADR-New-Quiz-Backend-EC2-2cc6c6c8e3f24723965ba08c430afd3f)
